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
from typing import Dict, List, Tuple, Optional, Any

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.state import SessionState
from agent.prompts import (
    MEMORY_UPDATE_ACKNOWLEDGMENT,
    QUERY_ANSWER_CHAT_PROMPT,
    GENERAL_RESPONSE_PROMPT,
    MISMATCH_VERIFICATION_PROMPT,
)
from agent.helpers import classify_fields_with_llm, create_llm, format_conversation_history
from agent.schemas import FieldClassification
from memory.sqlite_store import MemoryDatabase, VALID_COLUMNS
from memory.vector_store import VectorStore
from config import SQLITE_PATH, CHROMA_PATH

logger = logging.getLogger(__name__)


# ============================================================================
# DATE NORMALIZATION
# ============================================================================

def _normalize_date(value: Any) -> Optional[str]:
    """
    Normalize any date-like input into ISO YYYY-MM-DD.
    Indian convention: DD/MM/YYYY (dayfirst=True).
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    # Already YYYY-MM-DD
    if re.match(r'^\d{4}-\d{2}-\d{2}$', raw):
        try:
            from datetime import date as _d
            _d.fromisoformat(raw)
            return raw
        except ValueError:
            pass

    # python-dateutil (handles month names, ordinals, etc.)
    try:
        from dateutil import parser as du
        return du.parse(raw, dayfirst=True, yearfirst=False).strftime("%Y-%m-%d")
    except Exception:
        pass

    # Manual fallback: DD-MM-YYYY / DD/MM/YYYY / DD.MM.YYYY
    try:
        parts = re.split(r'[-/.]', raw)
        if len(parts) == 3:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            from datetime import date as _d
            return _d(y, m, d).strftime("%Y-%m-%d")
    except Exception:
        pass

    logger.warning(f"⚠️  _normalize_date: could not parse '{raw}'")
    return None


# ============================================================================
# FIELD VALIDATION
# ============================================================================

# Financial fields that need HITL confirmation before writing to SQLite
# Only field names that exist in VALID_COLUMNS (the SQLite schema) should appear here.
# Phantom names like 'annual_income', 'net_monthly_income', 'requested_loan_tenure',
# 'existing_loan_amount' are not DB columns — they were silently rejected by
# batch_update_fields and caused HITL confirmations that never actually saved anything.
FINANCIAL_FIELDS: frozenset = frozenset({
    "monthly_income",
    "cibil_score",
    "requested_loan_amount",
    "requested_loan_type",
    "requested_tenure_months",
    "total_existing_emi_monthly",
    "number_of_active_loans",
    "coapplicant_income",
})

_FIELD_RULES: Dict[str, Tuple[type, Optional[str]]] = {
    "monthly_income":             (float, None),
    "cibil_score":                (int,   "300-900"),
    "total_existing_emi_monthly": (float, None),
    "number_of_active_loans":     (int,   ">=0"),
    "requested_loan_amount":      (float, None),
    "requested_tenure_months":    (int,   ">0"),
    "years_at_job":               (float, None),
    "full_name":                  (str,   None),
    "phone":                      (str,   None),
    "city":                       (str,   None),
    "state":                      (str,   None),
    "pincode":                    (str,   None),
    "employer_name":              (str,   None),
    "job_title":                  (str,   None),
    "income_type":                (str,   None),
    "address":                    (str,   None),
    "requested_loan_type":        (str,   None),
    "loan_purpose":               (str,   None),
    "coapplicant_name":           (str,   None),
    "coapplicant_relation":       (str,   None),
    "coapplicant_income":         (float, None),
    "date_of_birth":              (str,   "date"),
}


def _validate_field(field_name: str, value: Any) -> Tuple[bool, Any, Optional[str]]:
    """Validate and coerce. Returns (is_valid, coerced_value, error_msg)."""
    if field_name not in _FIELD_RULES:
        return True, value, None
    if value is None:
        return False, None, "value is None"

    expected_type, rule = _FIELD_RULES[field_name]

    if field_name == "date_of_birth":
        normalized = _normalize_date(value)
        if normalized is None:
            return False, value, f"Cannot parse '{value}' as date"
        logger.info(f"📅 date_of_birth: '{value}' → '{normalized}'")
        return True, normalized, None

    try:
        coerced = expected_type(value)
    except (ValueError, TypeError):
        return False, value, f"{field_name}: cannot cast {value!r} to {expected_type.__name__}"

    if field_name == "cibil_score" and not (300 <= coerced <= 900):
        return False, coerced, "cibil_score must be 300-900"
    if field_name == "requested_tenure_months" and coerced <= 0:
        return False, coerced, "tenure must be > 0"
    if field_name == "number_of_active_loans" and coerced < 0:
        return False, coerced, "active loans must be >= 0"

    return True, coerced, None


# ============================================================================
# EXTRACT MEMORY NODE  (runs before router on EVERY turn)
# ============================================================================

async def extract_memory_node(state: SessionState) -> SessionState:
    """
    Universal extraction: classify → validate → write SQLite/ChromaDB → refresh context.
    Sets memory_mismatches and pending_fields in state when needed.
    """
    try:
        from memory.retriever import MemoryRetriever

        user_input  = (state.get("user_input") or "").strip()
        customer_id = (state.get("customer_id") or "").strip()
        session_id  = (state.get("session_id") or f"session_{datetime.now().timestamp()}").strip()

        if not user_input or not customer_id:
            return state

        # Reset transient per-turn state flags so they don't bleed across turns
        state["memory_mismatches"] = {}
        state["pending_fields"]    = {}

        messages     = state.get("messages") or []
        conv_history = format_conversation_history(messages[:-1]) if messages else "No prior conversation"
        memory_ctx   = state.get("memory_prompt_block", "No context available")

        # 1. Classify fields with LLM
        try:
            classifications: Dict[str, FieldClassification] = await classify_fields_with_llm(
                user_input=user_input,
                memory_context=memory_ctx,
                conversation_history=conv_history,
            )
        except Exception as e:
            logger.error(f"❌ Field classification failed: {e}")
            return state

        if not classifications:
            return state

        schema_fields: Dict[str, FieldClassification] = {}
        contextual_fields: Dict[str, FieldClassification] = {}
        for name, clf in classifications.items():
            (schema_fields if clf.field_type == "SCHEMA_FIELD" else contextual_fields)[name] = clf

        # 2. Validate + mismatch detection
        flat_facts: Dict[str, Any] = {}
        for group, fields in state.get("customer_facts", {}).items():
            if isinstance(fields, dict):
                flat_facts.update(fields)

        valid_schema: Dict[str, Any] = {}
        mismatches:   Dict[str, Any] = {}

        for field_name, clf in schema_fields.items():
            if field_name not in VALID_COLUMNS:
                contextual_fields[field_name] = clf
                continue

            is_valid, coerced_val, err_msg = _validate_field(field_name, clf.normalized_value)
            if not is_valid:
                logger.warning(f"⚠️  Skipping invalid '{field_name}': {err_msg}")
                continue

            old_val = flat_facts.get(field_name)
            old_str = str(old_val).strip() if old_val is not None else None
            new_str = str(coerced_val).strip()

            if old_str is not None and old_str != new_str and not getattr(clf, "is_correction", False):
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

        # 3. Split: immediate (identity/address) vs pending (financial, needs HITL)
        immediate_write: Dict[str, Any] = {}
        pending_fields:  Dict[str, Any] = {}
        for field_name, coerced_val in valid_schema.items():
            (pending_fields if field_name in FINANCIAL_FIELDS else immediate_write)[field_name] = coerced_val

        # Write immediately
        wrote_schema = False
        if immediate_write:
            try:
                with MemoryDatabase(db_path=SQLITE_PATH) as db:
                    db.init_schema()
                    db.batch_update_fields(customer_id=customer_id, fields=immediate_write)
                wrote_schema = True
                logger.info(f"   💾 SQLite immediate: {list(immediate_write.keys())}")
            except Exception as e:
                logger.error(f"❌ SQLite write failed: {e}")

        if pending_fields:
            state["pending_fields"] = pending_fields
            state["response_type"]  = "save_confirmation"
            logger.info(f"   ⏳ HITL pending: {list(pending_fields.keys())}")

        # 4. Write contextual info to ChromaDB
        wrote_chroma = False
        if contextual_fields:
            try:
                vs = VectorStore(persist_path=CHROMA_PATH)
                for field_name, clf in contextual_fields.items():
                    vs.add_chunk(
                        customer_id=customer_id,
                        session_id=session_id,
                        text=f"{clf.field_name or field_name}: {clf.raw_value}"[:500],
                        topic_tag=clf.category or "general",
                        extra_metadata={"type": "memory_update", "source": "extract_memory_node"},
                    )
                wrote_chroma = True
                logger.info(f"   🔍 ChromaDB: {len(contextual_fields)} contextual chunk(s)")
            except Exception as e:
                logger.warning(f"⚠️  ChromaDB write failed: {e}")

        # 5. Refresh memory_prompt_block if anything changed
        if wrote_schema or wrote_chroma:
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
