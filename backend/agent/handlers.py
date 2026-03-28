"""
Handler nodes for different types of customer interactions.

Handlers:
- extract_memory_node       : Universal extraction on every turn (SQLite + ChromaDB)
- handle_mismatch_confirmation : Ask user to verify conflicting data
- handle_save_confirmation  : HITL — ask user to confirm financial field saves
- handle_query              : Answer questions using profile + conversation history
- handle_general            : General conversation with full context injection
"""

import sys
import re
import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.state import SessionState
from agent.prompts import (
    MEMORY_UPDATE_ACKNOWLEDGMENT,
    QUERY_ANSWER_CHAT_PROMPT,
    GENERAL_RESPONSE_PROMPT,
    MISMATCH_VERIFICATION_PROMPT,
)
from agent.helpers import extract_fields_with_llm, create_llm, format_conversation_history
from memory.sqlite_store import MemoryDatabase
from memory.vector_store import VectorStore
from config import SQLITE_PATH, CHROMA_PATH

logger = logging.getLogger(__name__)



# ============================================================================
# FIELD VALIDATION
# ============================================================================

# Fields that require HITL confirmation before writing to SQLite.
# Rule: only NUMERICAL financial figures that directly affect eligibility/risk.
# Preferences and text fields (loan_type, tenure, purpose) are saved silently
# because they're not sensitive and users should be able to state them freely.
FINANCIAL_FIELDS: frozenset = frozenset({
    "monthly_income",            # direct income figure
    "cibil_score",               # credit score
    "requested_loan_amount",     # the rupee ask
    "total_existing_emi_monthly",# affects debt-to-income ratio
    "number_of_active_loans",    # affects eligibility
    "coapplicant_income",        # co-applicant income figure
    # NOT included: requested_loan_type, requested_tenure_months, loan_purpose
    # — these are preferences, not sensitive numerical data
})

# ──────────────────────────────────────────────────────────────────────────────
# Validation is now done by CustomerMemory.validate_partial (memory/models.py).
# Pydantic handles: type coercion, CIBIL range, positive numbers, date parsing,
# income_type normalisation, loan_type normalisation.
# _FIELD_RULES and _validate_field have been removed.
# ──────────────────────────────────────────────────────────────────────────────


# ============================================================================
# EXTRACT MEMORY NODE  (runs before router on EVERY turn)
# ============================================================================

async def extract_memory_node(state: SessionState) -> SessionState:
    """
    New clean pipeline:
      1. LLM extracts {key, value, is_correction} pairs from user input
      2. Route each pair:
           key in CustomerMemory.model_fields  →  Pydantic validate  →  SQLite
           key NOT in model_fields             →  contextual text    →  ChromaDB
      3. Financial fields (FINANCIAL_FIELDS) go to pending_fields (HITL) not immediate write
      4. Mismatch detection on all validated SQLite-bound fields
      5. Refresh memory_prompt_block if anything was written
    """
    try:
        from memory.retriever import MemoryRetriever
        from memory.models import CustomerMemory

        user_input  = (state.get("user_input") or "").strip()
        customer_id = (state.get("customer_id") or "").strip()
        session_id  = (state.get("session_id") or f"session_{datetime.now().timestamp()}").strip()

        if not user_input or not customer_id:
            return state

        # Reset transient per-turn state so previous turn doesn't bleed through
        state["memory_mismatches"] = {}
        state["pending_fields"]    = {}

        messages     = state.get("messages") or []
        conv_history = format_conversation_history(messages[:-1]) if messages else "No prior conversation"
        memory_ctx   = state.get("memory_prompt_block") or "No context available"

        # ── Step 1: Extract key-value pairs (LLM) ───────────────────────────
        extracted = await extract_fields_with_llm(
            user_input=user_input,
            memory_context=memory_ctx,
            conversation_history=conv_history,
        )

        if not extracted:
            return state

        # ── Step 2: Route — Pydantic model determines SQLite vs ChromaDB ────
        model_field_names = set(CustomerMemory.model_fields.keys())

        raw_sqlite:   Dict[str, Any]  = {}   # candidate SQLite fields (raw LLM values)
        contextual:   list            = []   # items destined for ChromaDB
        correction_flags: Dict[str, bool] = {}

        for field in extracted:
            if field.key in model_field_names:
                raw_sqlite[field.key] = field.value
                correction_flags[field.key] = field.is_correction
            else:
                contextual.append(field)    # not a schema field → ChromaDB

        # ── Step 3: Pydantic validation of SQLite-bound fields ───────────────
        pydantic_valid, pydantic_errors = CustomerMemory.validate_partial(raw_sqlite)

        for fname, err in pydantic_errors.items():
            logger.warning(f"⚠️  Validation failed '{fname}': {err}")
            # Demote failed fields to contextual so we don't silently lose them
            original = next((f for f in extracted if f.key == fname), None)
            if original:
                contextual.append(original)

        # ── Step 4: Mismatch detection ────────────────────────────────────────
        flat_facts: Dict[str, Any] = {}
        for group, fields in state.get("customer_facts", {}).items():
            if isinstance(fields, dict):
                flat_facts.update(fields)

        valid_schema:  Dict[str, Any] = {}
        mismatches:    Dict[str, Any] = {}

        for field_name, coerced_val in pydantic_valid.items():
            old_val       = flat_facts.get(field_name)
            is_correction = correction_flags.get(field_name, False)

            if old_val is not None and str(old_val).strip() != str(coerced_val).strip() and not is_correction:
                mismatches[field_name] = {
                    "old_value":   old_val,
                    "new_value":   coerced_val,
                    "explanation": f"New value '{coerced_val}' conflicts with stored '{old_val}'.",
                    "confidence":  0.95,
                }
            else:
                valid_schema[field_name] = coerced_val

        if mismatches:
            state["memory_mismatches"] = mismatches
            logger.info(f"⚠️  {len(mismatches)} conflict(s) detected")

        # ── Step 5: Split valid fields — immediate write vs HITL pending ─────
        immediate_write: Dict[str, Any] = {}
        pending_fields:  Dict[str, Any] = {}

        for field_name, coerced_val in valid_schema.items():
            if field_name in FINANCIAL_FIELDS:
                pending_fields[field_name] = coerced_val   # user must confirm
            else:
                immediate_write[field_name] = coerced_val  # safe to write now

        # Write non-financial fields immediately
        wrote_sqlite = False
        if immediate_write:
            try:
                with MemoryDatabase(db_path=SQLITE_PATH) as db:
                    db.init_schema()
                    db.batch_update_fields(customer_id=customer_id, fields=immediate_write)
                wrote_sqlite = True
                logger.info(f"   💾 SQLite immediate: {list(immediate_write.keys())}")
            except Exception as e:
                logger.error(f"❌ SQLite write failed: {e}")

        # Stage financial fields for user confirmation
        if pending_fields:
            state["pending_fields"] = pending_fields
            state["response_type"]  = "save_confirmation"
            logger.info(f"   ⏳ HITL pending: {list(pending_fields.keys())}")

        # ── Step 6: Write contextual chunks to ChromaDB ─────────────────────
        wrote_chroma = False
        if contextual:
            try:
                vs = VectorStore(persist_path=CHROMA_PATH)
                for f in contextual:
                    vs.add_chunk(
                        customer_id=customer_id,
                        session_id=session_id,
                        text=f"{f.key}: {f.value}"[:500],
                        topic_tag="general",
                        extra_metadata={"type": "contextual", "source": "extract_memory_node"},
                    )
                wrote_chroma = True
                logger.info(f"   🔍 ChromaDB: {len(contextual)} contextual chunk(s)")
            except Exception as e:
                logger.warning(f"⚠️  ChromaDB write failed: {e}")

        # ── Step 7: Refresh memory_prompt_block if anything changed ──────────
        if wrote_sqlite or wrote_chroma:
            try:
                retriever = MemoryRetriever(
                    db=MemoryDatabase(db_path=SQLITE_PATH),
                    vector_store=VectorStore(persist_path=CHROMA_PATH),
                )
                try:
                    ctx = retriever.build_context(
                        customer_id=customer_id,
                        current_turn=user_input,
                        n_chunks=3,
                    )
                    state["customer_facts"]      = retriever.db.get_all_facts_grouped(customer_id)
                    state["memory_prompt_block"] = ctx["prompt_block"]
                finally:
                    retriever.close()
            except Exception as e:
                logger.error(f"Failed to refresh memory block: {e}")

        return state

    except Exception as e:
        logger.error(f"❌ extract_memory_node crashed: {e}", exc_info=True)
        return state


# ============================================================================
# HANDLER: HANDLE_MISMATCH_CONFIRMATION
# ============================================================================

async def handle_mismatch_confirmation(state: SessionState) -> SessionState:
    """Ask user to confirm which value is correct when a conflict is detected."""
    try:
        mismatches     = state.get("memory_mismatches", {})
        dynamic_ctx    = state.get("dynamic_context", [])
        customer_facts = state.get("customer_facts", {})

        logger.info(f"🔍 Mismatch handler | {len(mismatches)} conflict(s)")

        if not mismatches:
            state["agent_response"] = "I thought there was a discrepancy, but everything looks fine. How can I help?"
            return state

        conflict_parts = []
        for field, info in mismatches.items():
            conflict_parts.append(
                f"• {field.replace('_', ' ').title()}\n"
                f"  On file  : {info.get('old_value', '?')}\n"
                f"  You said : {info.get('new_value', '?')}\n"
                f"  Note     : {info.get('explanation', '')} ({info.get('confidence', 0):.0%} confidence)"
            )

        historical_context = "a previous session"
        if dynamic_ctx:
            ctx_text = " ".join(dynamic_ctx[:2])
            days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            if any(d in ctx_text for d in days) or "ago" in ctx_text:
                historical_context = ctx_text[:200]

        llm   = create_llm(temperature=0.4)
        chain = MISMATCH_VERIFICATION_PROMPT | llm
        resp  = await chain.ainvoke({
            "mismatch_details":   "\n\n".join(conflict_parts),
            "historical_context": historical_context,
            "customer_profile":   json.dumps(customer_facts, indent=2) if customer_facts else "{}",
        })

        msg = resp.content if hasattr(resp, "content") else str(resp)
        state.update({
            "clarification_question": msg,
            "clarification_needed":   True,
            "agent_response":         msg,
            "response_type":          "mismatch_confirmation",
            "response_options":       ["✅ Yes, use new value", "❌ No, keep old value"],
        })
        return state

    except Exception as e:
        logger.error(f"❌ handle_mismatch_confirmation failed: {e}", exc_info=True)
        state["agent_response"] = (
            "I noticed some differences in your information. Could you confirm which values are correct?"
        )
        return state


# ============================================================================
# HANDLER: HANDLE_SAVE_CONFIRMATION  (HITL)
# ============================================================================

async def handle_save_confirmation(state: SessionState) -> SessionState:
    """
    Financial fields have been extracted and staged. Ask the user to confirm
    before writing to SQLite. Actual write happens via /confirm-save endpoint.
    """
    try:
        pending = state.get("pending_fields", {})
        if not pending:
            state["agent_response"] = "Got it! Is there anything else I can help you with?"
            state["response_type"]  = "text"
            return state

        LABELS = {
            "monthly_income": "Monthly Income", "annual_income": "Annual Income",
            "cibil_score": "CIBIL Score", "requested_loan_amount": "Requested Loan Amount",
            "requested_loan_type": "Loan Type", "total_existing_emi_monthly": "Total Monthly EMI",
            "number_of_active_loans": "Active Loans", "coapplicant_income": "Co-applicant Income",
        }
        lines = [f"• {LABELS.get(f, f.replace('_',' ').title())}: {v}" for f, v in pending.items()]

        state.update({
            "agent_response": (
                "I've noted the following financial details:\n\n"
                + "\n".join(lines)
                + "\n\nWould you like me to save this to your profile?"
            ),
            "response_type":    "save_confirmation",
            "response_options": ["✅ Save", "✏️ Edit", "❌ Don't Save"],
            # Clear mismatches so the next turn starts clean
            "memory_mismatches": {},
        })
        # NOTE: pending_fields intentionally kept in state so confirm-save endpoint
        # can read it via the SESSIONS dict (written back in send_message).
        # It gets cleared in confirm-save after the user responds.
        logger.info(f"📋 Save confirmation for {len(pending)} field(s)")
        return state

    except Exception as e:
        logger.error(f"❌ handle_save_confirmation failed: {e}", exc_info=True)
        state["agent_response"] = "I've noted your information. Shall I save it to your profile?"
        return state


# ============================================================================
# HANDLER: HANDLE_QUERY
# ============================================================================

async def handle_query(state: SessionState) -> SessionState:
    """
    Answer the user's question.
    Context = SQLite profile facts + ChromaDB contextual chunks + last N turns.
    """
    try:
        user_input     = state.get("user_input", "")
        memory_context = state.get("memory_prompt_block") or "No customer profile available."
        messages       = state.get("messages") or []

        # Last N turns of the CURRENT session (exclude the current user message)
        conv_history = format_conversation_history(messages[:-1], max_turns=6)

        llm   = create_llm(temperature=0.2)
        chain = QUERY_ANSWER_CHAT_PROMPT | llm

        response = await chain.ainvoke({
            "user_input":          user_input,
            "memory_context":      memory_context,
            "conversation_history": conv_history,
        })

        answer = response.content if hasattr(response, "content") else str(response)
        state.update({
            "query_response":  answer,
            "agent_response":  answer,
            "response_type":   "text",
            "response_options": ["📋 Check eligibility", "💬 Update profile", "❓ Ask another question"],
        })
        logger.info("💬 Query answered")
        return state

    except Exception as e:
        logger.error(f"❌ handle_query failed: {e}", exc_info=True)
        state["agent_response"] = "I'm unable to answer that right now. Please try again."
        return state


# ============================================================================
# HANDLER: HANDLE_GENERAL
# ============================================================================

async def handle_general(state: SessionState) -> SessionState:
    """
    General conversation — greetings, acknowledgments, small talk.
    Context = SQLite profile facts + ChromaDB contextual chunks + last N turns.
    """
    try:
        user_input     = state.get("user_input", "")
        memory_context = state.get("memory_prompt_block") or "No customer profile available."
        messages       = state.get("messages") or []

        # Last N turns of the CURRENT session (exclude the current user message)
        conv_history = format_conversation_history(messages[:-1], max_turns=6)

        llm   = create_llm(temperature=0.7)
        chain = GENERAL_RESPONSE_PROMPT | llm

        response = await chain.ainvoke({
            "user_input":          user_input,
            "memory_context":      memory_context,
            "conversation_history": conv_history,
        })

        answer = response.content if hasattr(response, "content") else str(response)
        state.update({
            "agent_response":  answer,
            "response_type":   "text",
            "response_options": ["💰 Check eligibility", "📋 View profile", "❓ Ask about loans"],
        })
        logger.info("💬 General response generated")
        return state

    except Exception as e:
        logger.error(f"❌ handle_general failed: {e}", exc_info=True)
        state["agent_response"] = "I encountered an error. Please try again."
        return state
