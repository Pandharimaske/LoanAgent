"""
Handler nodes for different types of customer interactions.

Handlers:
- handle_memory_update  : Classify user input → SQLite (schema fields) or ChromaDB (contextual)
- handle_mismatch_confirmation : Ask user to verify conflicting data
- handle_query          : Answer questions using facts + context
- handle_general        : General conversation with context injection
"""

import sys
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
from agent.helpers import classify_fields_with_llm, create_llm
from agent.schemas import FieldClassification
from memory.sqlite_store import MemoryDatabase
from memory.vector_store import VectorStore
from config import SQLITE_PATH, CHROMA_PATH

logger = logging.getLogger(__name__)
# ============================================================================
# FIELD VALIDATION HELPERS
# ============================================================================

# Per-field type + range rules used for pre-storage validation
_FIELD_RULES: Dict[str, Tuple[type, Optional[str]]] = {
    "monthly_income":              (float,  None),
    "cibil_score":                 (int,    "300-900"),
    "total_existing_emi_monthly":  (float,  None),
    "number_of_active_loans":      (int,    ">=0"),
    "requested_loan_amount":       (float,  None),
    "requested_tenure_months":     (int,    ">0"),
    "years_at_job":                (float,  None),
    "full_name":                   (str,    None),
    "phone":                       (str,    None),
    "city":                        (str,    None),
    "state":                       (str,    None),
    "pincode":                     (str,    None),
    "employer_name":               (str,    None),
    "job_title":                   (str,    None),
    "income_type":                 (str,    None),
    "address":                     (str,    None),
    "requested_loan_type":         (str,    None),
    "loan_purpose":                (str,    None),
    "coapplicant_name":            (str,    None),
    "coapplicant_relation":        (str,    None),
    "coapplicant_income":          (float,  None),
    "date_of_birth":               (str,    None),
}


def _validate_field(field_name: str, value: Any) -> Tuple[bool, Any, Optional[str]]:
    """
    Validate and coerce a single field value.
    Returns (is_valid, coerced_value, error_message).
    Unknown fields pass through (ChromaDB can store anything).
    """
    if field_name not in _FIELD_RULES:
        return True, value, None  # not a schema field — pass to ChromaDB

    expected_type, rule = _FIELD_RULES[field_name]

    # Attempt type coercion
    try:
        coerced = expected_type(value)
    except (ValueError, TypeError):
        return False, value, f"{field_name}: cannot convert {value!r} to {expected_type.__name__}"

    # Range checks
    if field_name == "cibil_score" and not (300 <= coerced <= 900):
        return False, coerced, "cibil_score must be 300-900"
    if field_name == "requested_tenure_months" and coerced <= 0:
        return False, coerced, "requested_tenure_months must be > 0"
    if field_name == "number_of_active_loans" and coerced < 0:
        return False, coerced, "number_of_active_loans must be >= 0"

    return True, coerced, None


# ============================================================================
# HANDLER 1: HANDLE_MEMORY_UPDATE
# ============================================================================

async def handle_memory_update(state: SessionState) -> SessionState:
    """
    Classify incoming user information and route each piece to the right store.

    Flow:
      1. Classify fields with LLM → SCHEMA_FIELD (SQLite) vs CONTEXTUAL_INFO (ChromaDB)
      2. Validate all SCHEMA fields before touching any DB
      3. FIX #4 — ensure customer row exists before UPDATE (batch_update_fields handles this)
      4. Batch-write schema fields to SQLite in a single transaction
      5. Write contextual info to ChromaDB
      6. Build response
    """
    try:
        user_input  = (state.get("user_input") or "").strip()
        customer_id = (state.get("customer_id") or "").strip()
        session_id  = (state.get("session_id") or f"session_{datetime.now().timestamp()}").strip()

        if not user_input:
            state["agent_response"] = "I didn't receive any information to process."
            return state
        if not customer_id:
            logger.error("❌ Missing customer_id in state")
            state["agent_response"] = "Error: Unable to identify customer."
            return state

        logger.info(f"📝 Memory Update | {customer_id} | '{user_input[:60]}…'")

        # ------------------------------------------------------------------
        # Step 1 — Classify fields with LLM
        # ------------------------------------------------------------------
        try:
            classifications: Dict[str, FieldClassification] = await classify_fields_with_llm(user_input)
        except Exception as e:
            logger.error(f"❌ Field classification failed: {e}")
            state["agent_response"] = "I had trouble understanding that. Could you rephrase?"
            return state

        if not classifications:
            # LLM found nothing structured — treat as general/contextual note
            logger.info("ℹ️  No structured fields found — storing as contextual chunk")
            _store_contextual_chunk(customer_id, session_id, user_input, "general_note")
            state["agent_response"] = "Got it! I've noted that for reference."
            state["memory_updates"] = []
            return state

        schema_fields: Dict[str, FieldClassification] = {}
        contextual_fields: Dict[str, FieldClassification] = {}

        for name, clf in classifications.items():
            if clf.field_type == "SCHEMA_FIELD":
                schema_fields[name] = clf
            else:
                contextual_fields[name] = clf

        logger.info(f"   Schema: {len(schema_fields)} | Contextual: {len(contextual_fields)}")

        # ------------------------------------------------------------------
        # Step 2 — Validate all schema fields (fail-fast before any writes)
        # ------------------------------------------------------------------
        valid_schema: Dict[str, Any] = {}
        validation_errors: Dict[str, str] = {}

        for field_name, clf in schema_fields.items():
            # Only attempt to store fields that actually exist in the DB schema
            if field_name not in VALID_COLUMNS:
                logger.warning(f"⚠️  '{field_name}' not in DB schema — routing to ChromaDB")
                contextual_fields[field_name] = clf
                continue

            is_valid, coerced_val, error_msg = _validate_field(
                field_name, clf.normalized_value
            )
            if is_valid:
                valid_schema[field_name] = coerced_val
            else:
                validation_errors[field_name] = error_msg or "Validation failed"
                logger.warning(f"   ❌ {field_name}: {error_msg}")

        if not valid_schema and schema_fields:
            err_list = "; ".join(f"{k}: {v}" for k, v in list(validation_errors.items())[:3])
            state["agent_response"] = f"I couldn't process some details: {err_list}. Please clarify?"
            return state

        # ------------------------------------------------------------------
        # Step 3+4 — Batch-write schema fields to SQLite
        # FIX #4 is inside batch_update_fields (ensure_customer_exists guard)
        # ------------------------------------------------------------------
        sqlite_results: Dict[str, bool] = {}
        if valid_schema:
            try:
                with MemoryDatabase(db_path=SQLITE_PATH) as db:
                    db.init_schema()
                    sqlite_results = db.batch_update_fields(
                        customer_id=customer_id,
                        fields=valid_schema,
                    )
                ok = sum(1 for v in sqlite_results.values() if v)
                logger.info(f"   💾 SQLite: {ok}/{len(valid_schema)} fields written")
            except Exception as e:
                logger.error(f"❌ SQLite batch write failed: {e}")
                for k in valid_schema:
                    sqlite_results[k] = False

        # ------------------------------------------------------------------
        # Step 5 — Write contextual info to ChromaDB
        # ------------------------------------------------------------------
        chroma_count = 0
        if contextual_fields:
            try:
                vs = VectorStore(persist_path=CHROMA_PATH)
                for field_name, clf in contextual_fields.items():
                    chunk_text = f"{clf.field_name or field_name}: {clf.raw_value}"
                    vs.add_chunk(
                        customer_id=customer_id,
                        session_id=session_id,
                        text=chunk_text[:500],
                        topic_tag=clf.category or "general",
                        extra_metadata={
                            "type":        "memory_update",
                            "category":    clf.category or "general",
                            "source":      "handle_memory_update",
                            "original":    clf.raw_value,
                        },
                    )
                    chroma_count += 1
                logger.info(f"   🔍 ChromaDB: {chroma_count} contextual chunks stored")
            except Exception as e:
                logger.error(f"❌ ChromaDB write failed: {e}")

        # ------------------------------------------------------------------
        # Step 6 — Build response
        # ------------------------------------------------------------------
        parts = [MEMORY_UPDATE_ACKNOWLEDGMENT]

        saved_fields = [f for f, ok in sqlite_results.items() if ok]
        if saved_fields:
            parts.append(f"Saved: {', '.join(saved_fields)}.")
        if chroma_count:
            parts.append(f"Also noted {chroma_count} additional detail(s).")
        if validation_errors:
            issues = "; ".join(f"{k}: {v}" for k, v in list(validation_errors.items())[:2])
            parts.append(f"(Could not process: {issues})")

        state["agent_response"] = " ".join(parts)
        state["memory_updates"] = [
            {"field": f, "value": v, "type": "schema", "status": "pending"}
            for f, v in valid_schema.items()
        ] + [
            {"field": clf.field_name or k, "value": clf.raw_value, "type": "contextual"}
            for k, clf in contextual_fields.items()
        ]

        logger.info(
            f"✅ Memory update done | {len(saved_fields)} SQLite + {chroma_count} ChromaDB "
            f"| {len(validation_errors)} failed"
        )
        return state

    except Exception as e:
        logger.error(f"❌ handle_memory_update crashed: {e}", exc_info=True)
        state["agent_response"] = "I encountered an error storing that information. Please try again."
        return state


def _store_contextual_chunk(
    customer_id: str,
    session_id: str,
    text: str,
    topic_tag: str,
) -> None:
    """Helper: store a single text chunk to ChromaDB, swallowing errors."""
    try:
        vs = VectorStore(persist_path=CHROMA_PATH)
        vs.add_chunk(
            customer_id=customer_id,
            session_id=session_id,
            text=text[:500],
            topic_tag=topic_tag,
        )
    except Exception as e:
        logger.warning(f"⚠️  Contextual chunk store failed: {e}")


# ============================================================================
# HANDLER 2: HANDLE_MISMATCH_CONFIRMATION
# ============================================================================

async def handle_mismatch_confirmation(state: SessionState) -> SessionState:
    """
    User provided info that CONFLICTS with existing stored data.
    Show the user a clear picture of what we have vs what they said,
    and ask them to confirm which value is correct.

    If no real mismatches found (router over-triggered), delegate to
    handle_memory_update so data is never silently dropped.
    """
    try:
        mismatches      = state.get("mismatched_fields", {})
        dynamic_context = state.get("dynamic_context", [])
        customer_facts  = state.get("customer_facts", {})

        logger.info(f"🔍 Mismatch handler | {len(mismatches)} conflict(s)")

        if not mismatches:
            # Router over-triggered — no actual conflict found. Treat as memory update.
            logger.warning("⚠️  No mismatches found — delegating to handle_memory_update")
            return await handle_memory_update(state)

        # Build human-readable conflict details
        conflict_parts: List[str] = []
        for field, info in mismatches.items():
            old_val    = info.get("old_value", "unknown")
            new_val    = info.get("new_value", "unknown")
            explanation = info.get("explanation", "Value changed")
            confidence  = info.get("confidence", 0.0)

            conflict_parts.append(
                f"• {field.replace('_', ' ').title()}\n"
                f"  On file  : {old_val}\n"
                f"  You said : {new_val}\n"
                f"  Note     : {explanation} (confidence: {confidence:.0%})"
            )

        mismatch_details = "\n\n".join(conflict_parts)

        # Historical context hint (extract rough date from ChromaDB text)
        historical_context = "a previous session"
        if dynamic_context:
            ctx_text = " ".join(dynamic_context[:2])
            days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
            if any(d in ctx_text for d in days) or "ago" in ctx_text:
                historical_context = ctx_text[:200]

        customer_profile = json.dumps(customer_facts, indent=2) if customer_facts else "{}"

        llm   = create_llm(temperature=0.4)
        chain = MISMATCH_VERIFICATION_PROMPT | llm

        response = await chain.ainvoke({
            "mismatch_details":   mismatch_details,
            "historical_context": historical_context,
            "customer_profile":   customer_profile,
        })

        confirmation_msg = (
            response.content if hasattr(response, "content") else str(response)
        )

        state["clarification_question"] = confirmation_msg
        state["clarification_needed"]   = True
        state["agent_response"]         = confirmation_msg

        logger.info(f"❓ Mismatch confirmation sent for {len(mismatches)} field(s)")
        return state

    except Exception as e:
        logger.error(f"❌ handle_mismatch_confirmation failed: {e}", exc_info=True)
        state["agent_response"] = (
            "I noticed some differences in the information you provided versus what we have on file. "
            "Could you please confirm your current details so we can keep your profile accurate?"
        )
        return state


# ============================================================================
# HANDLER 3: HANDLE_QUERY
# ============================================================================

async def handle_query(state: SessionState) -> SessionState:
    """
    Answer the user's question using confirmed facts + ChromaDB context.
    Low temperature for factual accuracy.
    """
    try:
        user_input       = state.get("user_input", "")
        memory_block     = state.get("memory_prompt_block") or ""
        customer_facts   = state.get("customer_facts", {})
        context          = state.get("dynamic_context", [])[:3]

        facts_summary    = json.dumps(customer_facts, indent=2) if customer_facts else "No customer profile yet."
        context_summary  = memory_block if memory_block else "\n".join(context) if context else "No relevant context."

        llm   = create_llm(temperature=0.2)
        chain = QUERY_ANSWER_CHAT_PROMPT | llm

        response = await chain.ainvoke({
            "user_input":      user_input,
            "facts_summary":   facts_summary,
            "context_summary": context_summary,
        })

        answer = response.content if hasattr(response, "content") else str(response)

        state["query_response"] = answer
        state["agent_response"] = answer
        logger.info("💬 Query answered")
        return state

    except Exception as e:
        logger.error(f"❌ handle_query failed: {e}", exc_info=True)
        state["agent_response"] = (
            "I'm unable to answer that question right now. Please try again."
        )
        return state


# ============================================================================
# HANDLER 4: HANDLE_GENERAL
# ============================================================================

async def handle_general(state: SessionState) -> SessionState:
    """
    General conversation handler with context injection.
    Slightly higher temperature for a conversational feel.
    """
    try:
        user_input      = state.get("user_input", "")
        memory_block    = state.get("memory_prompt_block") or ""
        customer_facts  = state.get("customer_facts", {})
        context         = state.get("dynamic_context", [])[:2]

        facts_summary   = json.dumps(customer_facts, indent=2) if customer_facts else "No customer profile yet."
        context_summary = memory_block if memory_block else "\n".join(context) if context else "No previous context."

        llm   = create_llm(temperature=0.7)
        chain = GENERAL_RESPONSE_PROMPT | llm

        response = await chain.ainvoke({
            "user_input":      user_input,
            "facts_summary":   facts_summary,
            "context_summary": context_summary,
        })

        answer = response.content if hasattr(response, "content") else str(response)

        state["agent_response"] = answer
        logger.info("💬 General response sent")
        return state

    except Exception as e:
        logger.error(f"❌ handle_general failed: {e}", exc_info=True)
        state["agent_response"] = (
            "I encountered an error processing your request. Please try again."
        )
        return state
