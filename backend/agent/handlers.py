"""
Handler nodes for different types of customer interactions.

Handlers:
- handle_memory_update  : Classify user input → SQLite (schema fields) or ChromaDB (contextual)
- handle_mismatch_confirmation : Ask user to verify conflicting data
- handle_query          : Answer questions using facts + context
- handle_general        : General conversation with context injection
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
    Normalize any date-like input into ISO format YYYY-MM-DD.

    Handles common user formats:
      - DD-MM-YYYY  e.g. "5-3-2005"  or "05-03-2005"
      - DD/MM/YYYY  e.g. "5/3/2005"  (default Indian convention — dayfirst)
      - DD.MM.YYYY  e.g. "05.03.2005"
      - YYYY-MM-DD  (already correct — pass-through)
      - Month names e.g. "March 5 2005" / "5 March 2005" / "5th March, 2005"

    Returns:
        ISO date string "YYYY-MM-DD" on success, or None if unparseable.
    """
    if value is None:
        return None

    raw = str(value).strip()
    if not raw:
        return None

    # 1. Already YYYY-MM-DD — validate calendar and return
    if re.match(r'^\d{4}-\d{2}-\d{2}$', raw):
        try:
            from datetime import date as _date
            _date.fromisoformat(raw)
            return raw
        except ValueError:
            pass  # fall through to other parsers

    # 2. Try python-dateutil (handles month names, ordinals, etc.)
    #    dayfirst=True  → treat "5/3/2005" as 5th March (Indian convention)
    #    yearfirst=False → don't treat leading 4-digit as year when ambiguous
    try:
        from dateutil import parser as du_parser
        parsed = du_parser.parse(raw, dayfirst=True, yearfirst=False)
        return parsed.strftime("%Y-%m-%d")
    except Exception:
        pass

    # 3. Manual fallback for strict DD-MM-YYYY / DD/MM/YYYY / DD.MM.YYYY
    try:
        parts = re.split(r'[-/.]', raw)
        if len(parts) == 3:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            from datetime import date as _date
            return _date(y, m, d).strftime("%Y-%m-%d")
    except Exception:
        pass

    logger.warning(f"⚠️  _normalize_date: could not parse '{raw}'")
    return None


# ============================================================================
# PER-FIELD VALIDATION RULES
# ============================================================================

# Fields that require user confirmation before writing to SQLite (HITL).
# Personal identity data (name, DOB, phone) is saved silently.
# Financial and loan-related data is held as pending until user approves.
FINANCIAL_FIELDS: frozenset = frozenset({
    "monthly_income",
    "annual_income",
    "net_monthly_income",
    "cibil_score",
    "requested_loan_amount",
    "requested_loan_type",
    "requested_loan_tenure",
    "existing_loan_amount",
    "total_existing_emi_monthly",
    "number_of_active_loans",
    "coapplicant_income",
})

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
    # date_of_birth handled specially — goes through _normalize_date
    "date_of_birth":               (str,    "date"),
}


def _validate_field(field_name: str, value: Any) -> Tuple[bool, Any, Optional[str]]:
    """
    Validate and coerce a single field value.

    Special handling:
    - date_of_birth: normalized to YYYY-MM-DD via _normalize_date(), regardless
      of how the LLM or user expressed it (DD-MM-YYYY, DD/MM/YYYY, month names …)

    Returns (is_valid, coerced_value, error_message).
    Unknown fields pass through (ChromaDB can store anything).
    """
    if field_name not in _FIELD_RULES:
        return True, value, None  # not a schema field — pass to ChromaDB

    if value is None:
        return False, None, "value is missing or empty"

    expected_type, rule = _FIELD_RULES[field_name]

    # ── Special case: date_of_birth ──────────────────────────────────────────
    if field_name == "date_of_birth":
        normalized = _normalize_date(value)
        if normalized is None:
            return False, value, f"date_of_birth: cannot parse '{value}' as a date"
        logger.info(f"📅 date_of_birth normalized: '{value}' → '{normalized}'")
        return True, normalized, None

    # ── Generic coercion ─────────────────────────────────────────────────────
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
# EXTRACT MEMORY NODE (runs before router on every turn)
# ============================================================================

async def extract_memory_node(state: SessionState) -> SessionState:
    """
    UNIVERSAL EXTRACTION NODE:
    Runs on every turn before the router.
    1. Extracts fields via LLM (classify_fields_with_llm).
    2. Programmatically normalizes and validates each field (incl. date_of_birth).
    3. Checks for mismatches against existing facts.
    4. Writes new/non-conflicting facts directly to SQLite/Chroma.
    5. Regenerates the memory_prompt_block.
    """
    try:
        from memory.retriever import MemoryRetriever

        user_input  = (state.get("user_input") or "").strip()
        customer_id = (state.get("customer_id") or "").strip()
        session_id  = (state.get("session_id") or f"session_{datetime.now().timestamp()}").strip()

        if not user_input or not customer_id:
            return state

        messages = state.get("messages") or []
        conv_history = format_conversation_history(messages[:-1]) if messages else "No prior conversation"
        memory_context = state.get("memory_prompt_block", "No context available")

        # Step 1: Classify fields via LLM
        try:
            classifications: Dict[str, FieldClassification] = await classify_fields_with_llm(
                user_input=user_input,
                memory_context=memory_context,
                conversation_history=conv_history
            )
        except Exception as e:
            logger.error(f"❌ Field classification failed: {e}")
            return state

        if not classifications:
            return state

        schema_fields: Dict[str, FieldClassification] = {}
        contextual_fields: Dict[str, FieldClassification] = {}

        for name, clf in classifications.items():
            if clf.field_type == "SCHEMA_FIELD":
                schema_fields[name] = clf
            else:
                contextual_fields[name] = clf

        # Step 2: Validate / normalize + detect mismatches
        valid_schema: Dict[str, Any] = {}
        mismatches: Dict[str, Any] = {}

        # Flatten existing facts for comparison
        flat_facts: Dict[str, Any] = {}
        for group, fields in state.get("customer_facts", {}).items():
            if isinstance(fields, dict):
                flat_facts.update(fields)

        for field_name, clf in schema_fields.items():
            if field_name not in VALID_COLUMNS:
                contextual_fields[field_name] = clf
                continue

            # _validate_field handles date_of_birth normalization internally
            is_valid, coerced_val, err_msg = _validate_field(field_name, clf.normalized_value)
            if not is_valid:
                logger.warning(f"⚠️  Skipping invalid field '{field_name}': {err_msg}")
                continue

            old_val = flat_facts.get(field_name)

            # Mismatch check (normalize both sides for date fields before comparing)
            old_str = str(old_val).strip() if old_val is not None else None
            new_str = str(coerced_val).strip()

            if old_str is not None and old_str != new_str and not getattr(clf, 'is_correction', False):
                mismatches[field_name] = {
                    "old_value": old_val,
                    "new_value": coerced_val,
                    "explanation": (
                        f"Detected new value '{coerced_val}' conflicting with "
                        f"existing record '{old_val}'."
                    ),
                    "confidence": 0.95,
                }
            else:
                valid_schema[field_name] = coerced_val

        if mismatches:
            state["memory_mismatches"] = mismatches
            logger.info(f"⚠️  Programmatic conflict detection: {len(mismatches)} conflict(s) flagged.")

        # Step 3: Split valid fields — financial fields go to pending (HITL), rest write immediately
        immediate_write: Dict[str, Any] = {}
        pending_fields:  Dict[str, Any] = {}

        for field_name, coerced_val in valid_schema.items():
            if field_name in FINANCIAL_FIELDS:
                pending_fields[field_name] = coerced_val
            else:
                immediate_write[field_name] = coerced_val

        # Write non-financial fields immediately (name, DOB, phone, address, etc.)
        wrote_schema = False
        if immediate_write:
            try:
                with MemoryDatabase(db_path=SQLITE_PATH) as db:
                    db.init_schema()
                    db.batch_update_fields(customer_id=customer_id, fields=immediate_write)
                wrote_schema = True
                logger.info(f"   💾 SQLite (immediate): {list(immediate_write.keys())}")
            except Exception as e:
                logger.error(f"❌ SQLite batch write failed: {e}")

        # Stage financial fields as pending (user must confirm)
        if pending_fields:
            state["pending_fields"] = pending_fields
            state["response_type"]  = "save_confirmation"
            logger.info(f"   ⏳ Pending (HITL): {list(pending_fields.keys())}")


        # Step 4: Write contextual info to ChromaDB
        wrote_chroma = False
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
                            "type": "memory_update",
                            "source": "extract_memory_node",
                        },
                    )
                wrote_chroma = True
                logger.info(f"   🔍 ChromaDB: {len(contextual_fields)} contextual chunk(s) stored")
            except Exception as e:
                logger.warning(f"⚠️  ChromaDB write failed: {e}")

        # Step 5: Regenerate context block if anything changed
        if wrote_schema or wrote_chroma:
            try:
                db = MemoryDatabase(db_path=SQLITE_PATH)
                retriever = MemoryRetriever(db)
                context_payload = retriever.build_context(
                    customer_id=customer_id,
                    current_turn=user_input,
                    n_chunks=3,
                )
                state["customer_facts"]      = db.get_all_facts_grouped(customer_id)
                state["memory_prompt_block"] = context_payload["prompt_block"]
                db.close()
            except Exception as e:
                logger.error(f"Failed to rebuild memory block: {e}")

        return state

    except Exception as e:
        logger.error(f"❌ extract_memory_node logic crashed: {e}", exc_info=True)
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
# HANDLER: HANDLE_MISMATCH_CONFIRMATION
# ============================================================================

async def handle_mismatch_confirmation(state: SessionState) -> SessionState:
    """
    User provided info that CONFLICTS with existing stored data.
    Show the user a clear picture of what we have vs what they said,
    and ask them to confirm which value is correct.
    """
    try:
        mismatches      = state.get("memory_mismatches", {})
        dynamic_context = state.get("dynamic_context", [])
        customer_facts  = state.get("customer_facts", {})

        logger.info(f"🔍 Mismatch handler | {len(mismatches)} conflict(s)")

        if not mismatches:
            logger.warning("⚠️  mismatches is empty but handler was called!")
            state["agent_response"] = (
                "I thought there was a discrepancy with your data, but it seems fine. Moving on!"
            )
            return state

        # Build human-readable conflict details
        conflict_parts: List[str] = []
        for field, info in mismatches.items():
            old_val     = info.get("old_value", "unknown")
            new_val     = info.get("new_value", "unknown")
            explanation = info.get("explanation", "Value changed")
            confidence  = info.get("confidence", 0.0)

            conflict_parts.append(
                f"• {field.replace('_', ' ').title()}\n"
                f"  On file  : {old_val}\n"
                f"  You said : {new_val}\n"
                f"  Note     : {explanation} (confidence: {confidence:.0%})"
            )

        mismatch_details = "\n\n".join(conflict_parts)

        historical_context = "a previous session"
        if dynamic_context:
            ctx_text = " ".join(dynamic_context[:2])
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
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
        state["response_type"]          = "mismatch_confirmation"
        state["response_options"]       = ["✅ Yes, use the new value", "❌ No, keep my old value"]

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
# HANDLER: HANDLE_SAVE_CONFIRMATION
# ============================================================================

async def handle_save_confirmation(state: SessionState) -> SessionState:
    """
    Runs when extract_memory_node has set pending_fields (financial data).
    Generates a confirmation message summarizing what will be saved.
    The actual write happens via the /confirm-save API endpoint.
    """
    try:
        pending = state.get("pending_fields", {})
        if not pending:
            # Nothing pending — fall through to general
            state["agent_response"] = "Got it! Is there anything else I can help you with?"
            state["response_type"]  = "text"
            return state

        # Format the pending fields as human-readable
        field_lines = []
        field_labels = {
            "monthly_income":            "Monthly Income",
            "annual_income":             "Annual Income",
            "net_monthly_income":        "Net Monthly Income",
            "cibil_score":               "CIBIL Score",
            "requested_loan_amount":     "Requested Loan Amount",
            "requested_loan_type":       "Loan Type",
            "requested_loan_tenure":     "Loan Tenure",
            "existing_loan_amount":      "Existing Loan Amount",
            "total_existing_emi_monthly": "Total Monthly EMI",
            "number_of_active_loans":    "Active Loans",
            "coapplicant_income":        "Co-applicant Income",
        }
        for field, value in pending.items():
            label = field_labels.get(field, field.replace("_", " ").title())
            field_lines.append(f"• {label}: {value}")

        fields_summary = "\n".join(field_lines)
        msg = (
            f"I've noted the following financial details from our conversation:\n\n"
            f"{fields_summary}\n\n"
            f"Would you like me to save this to your profile?"
        )

        state["agent_response"]   = msg
        state["response_type"]    = "save_confirmation"
        state["response_options"] = ["✅ Save", "✏️ Edit", "❌ Don't Save"]

        logger.info(f"📋 Save confirmation card generated for {len(pending)} field(s)")
        return state

    except Exception as e:
        logger.error(f"❌ handle_save_confirmation failed: {e}", exc_info=True)
        state["agent_response"] = "I've noted your information. Is there anything else I can help you with?"
        return state


# ============================================================================
# HANDLER: HANDLE_QUERY
# ============================================================================

async def handle_query(state: SessionState) -> SessionState:
    """
    Answer the user's question using confirmed facts + ChromaDB context.
    Low temperature for factual accuracy.
    """
    try:
        user_input     = state.get("user_input", "")
        memory_context = state.get("memory_prompt_block", "No context available")

        llm   = create_llm(temperature=0.2)
        chain = QUERY_ANSWER_CHAT_PROMPT | llm

        response = await chain.ainvoke({
            "user_input":     user_input,
            "memory_context": memory_context,
        })

        answer = response.content if hasattr(response, "content") else str(response)

        state["query_response"] = answer
        state["agent_response"] = answer
        state["response_type"]  = "text"
        state["response_options"] = ["📋 Check eligibility", "💬 Update my profile", "❓ Ask another question"]
        logger.info("💬 Query answered")
        return state

    except Exception as e:
        logger.error(f"❌ handle_query failed: {e}", exc_info=True)
        state["agent_response"] = (
            "I'm unable to answer that question right now. Please try again."
        )
        return state


# ============================================================================
# HANDLER: HANDLE_GENERAL
# ============================================================================

async def handle_general(state: SessionState) -> SessionState:
    """
    General conversation handler with context injection.
    Slightly higher temperature for a conversational feel.
    """
    try:
        user_input     = state.get("user_input", "")
        memory_context = state.get("memory_prompt_block", "No context available")

        llm   = create_llm(temperature=0.7)
        chain = GENERAL_RESPONSE_PROMPT | llm

        response = await chain.ainvoke({
            "user_input":     user_input,
            "memory_context": memory_context,
        })

        answer = response.content if hasattr(response, "content") else str(response)

        state["agent_response"] = answer
        state["response_type"]  = "text"
        state["response_options"] = ["💰 Check loan eligibility", "📋 View my profile", "❓ Ask about loans"]
        logger.info("💬 General response generated")
        return state

    except Exception as e:
        logger.error(f"❌ handle_general failed: {e}", exc_info=True)
        state["agent_response"] = (
            "I encountered an error processing your request. Please try again."
        )
        return state
