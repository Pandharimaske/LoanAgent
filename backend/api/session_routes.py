"""
Session orchestration routes.

Thin wrapper around the LangGraph agent.
All state (messages, pending_fields, tokens) is kept in the shared SESSIONS
dict that lives in chat_routes — so /confirm-save always finds the right data.
"""

import hashlib
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.graph import get_graph, run_session
from agent.state import SessionState
from agent.language import detect_language, translate_to_english, translate_to_user_language, _looks_like_english
from agent.helpers import create_llm
from auth.user_store import UserDatabase
from config import SQLITE_PATH

# ── Import the shared session store from chat_routes ──────────────────────────
# Both /session/message and /chat/confirm-save must operate on the SAME dict.
from api.chat_routes import SESSIONS, _create_session, _count_tokens_approx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/session", tags=["session"])


# ============================================================================
# REQUEST / RESPONSE SCHEMAS
# ============================================================================

class SessionStartRequest(BaseModel):
    session_id:  Optional[str] = None
    customer_id: str
    language:    Optional[str] = "en"


class SessionStartResponse(BaseModel):
    success:     bool
    session_id:  str
    customer_id: str
    started_at:  str
    message:     str


class MessageRequest(BaseModel):
    session_id: str
    user_input: str
    language:   Optional[str] = "en"


class MessageResponse(BaseModel):
    success:                bool
    session_id:             str
    user_input:             str
    agent_response:         str
    # HITL / quick-reply fields (must match ChatResponse in chat_routes)
    response_type:          Optional[str]            = "text"
    response_options:       Optional[List[str]]       = None
    pending_fields:         Optional[Dict[str, Any]] = None
    # Extra metadata
    detected_intent:        Optional[str]            = None
    clarification_question: Optional[str]            = None
    total_tokens:           Optional[int]            = None
    should_summarize:       Optional[bool]           = None
    has_mismatch:           Optional[bool]           = None
    mismatched_fields:      Optional[Dict[str, Any]] = None
    error:                  Optional[str]            = None


class SessionStateResponse(BaseModel):
    success:     bool
    session_id:  str
    customer_id: str
    state:       Dict[str, Any]


# ============================================================================
# HELPERS
# ============================================================================

def _resolve_customer_id(session_id: str) -> str:
    """
    Derive a stable customer_id from the auth session stored in the DB.
    Falls back to a hash of the user_id so it is always deterministic.
    Always calls init_user_schema() first so the messages/summary migration
    columns exist before any read/write.
    """
    try:
        with UserDatabase(db_path=SQLITE_PATH) as db:
            db.init_user_schema()   # ensure messages + summary columns exist
            user_session = db.get_session(session_id)
            if user_session and user_session.customer_id:
                return user_session.customer_id
            if user_session:
                user = db.get_user(user_session.user_id)
                if user and user.email:
                    return (
                        "CUST_"
                        + hashlib.sha256(user.email.lower().encode())
                        .hexdigest()[:8]
                        .upper()
                    )
                return f"CUST_{user_session.user_id[-8:].upper()}"
    except Exception as e:
        logger.warning(f"⚠️  Could not resolve customer_id: {e}")
    return "demo_customer"


# ============================================================================
# ROUTES
# ============================================================================

@router.post("/start", response_model=SessionStartResponse)
async def start_session(request: SessionStartRequest):
    """Create (or acknowledge) a session and return its ID."""
    try:
        session_id  = request.session_id or str(uuid.uuid4())
        customer_id = request.customer_id
        language    = request.language or "en"

        # Ensure an entry exists in the shared SESSIONS store
        if session_id not in SESSIONS:
            _create_session(customer_id, language, session_id=session_id)

        return SessionStartResponse(
            success=True,
            session_id=session_id,
            customer_id=customer_id,
            started_at=datetime.now().isoformat(),
            message=f"Session {session_id} started for customer {customer_id}",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start session: {e}")


@router.post("/message", response_model=MessageResponse)
async def send_message(request: MessageRequest):
    """
    Send one user turn through the LangGraph agent.

    Key guarantees:
    • customer_id resolved from the auth session in DB.
    • Prior messages loaded from the shared SESSIONS store (survives restarts via DB seed).
    • pending_fields written back to SESSIONS so /chat/confirm-save can read them.
    • Full rich response returned (response_type, response_options, pending_fields).
    """
    session_id  = request.session_id
    customer_id = _resolve_customer_id(session_id)

    # ── Ensure session exists in shared store ───────────────────────────────
    if session_id not in SESSIONS:
        _create_session(customer_id, request.language or "en", session_id=session_id)

    session_data   = SESSIONS[session_id]
    prior_messages: List[Dict[str, Any]] = list(session_data.get("messages", []))
    prior_tokens:   int                  = session_data.get("total_tokens", 0)

    logger.info(
        f"📨 [session/{session_id[:8]}] '{request.user_input[:60]}' "
        f"| customer={customer_id} | msgs={len(prior_messages)}"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # LANGUAGE DETECTION + TRANSLATE-IN
    # Mirrors the logic in chat_routes.py so /session/message has the same
    # Hindi support as /chat/message.
    # ─────────────────────────────────────────────────────────────────────────
    raw_input      = request.user_input
    translate_llm  = create_llm(temperature=0.1)
    session_lang   = session_data.get("language", "auto")
    preferred_lang = session_data.get("preferred_language", None)

    req_lang = request.language or "auto"
    if req_lang not in ("auto", "AUTO", None, ""):
        # Frontend sent an explicit language lock
        detected_lang = req_lang
        if detected_lang != "en":
            SESSIONS[session_id]["preferred_language"] = detected_lang
    elif session_lang not in ("auto", "AUTO", None, ""):
        detected_lang = session_lang
        if detected_lang != "en":
            SESSIONS[session_id]["preferred_language"] = detected_lang
    else:
        message_lang = detect_language(raw_input)
        if message_lang != "en":
            detected_lang = message_lang
            SESSIONS[session_id]["preferred_language"] = message_lang
        elif preferred_lang and preferred_lang != "en":
            detected_lang = preferred_lang
        else:
            detected_lang = "en"

    english_input = await translate_to_english(raw_input, detected_lang, translate_llm)
    SESSIONS[session_id]["language"] = detected_lang
    logger.info(f"🌐 [session] Language: '{detected_lang}' (sticky={preferred_lang}) | translated={detected_lang != 'en'}")

    # ── Build LangGraph initial state ───────────────────────────────────────
    initial_state: SessionState = {
        "session_id":  session_id,
        "customer_id": customer_id,
        "user_input":  english_input,   # pipeline always runs in English
        "language":    detected_lang,
        "messages":    prior_messages,

        # Memory (filled by load_memory node)
        "customer_facts":      {},
        "dynamic_context":     [],
        "session_summaries":   [],
        "memory_prompt_block": None,

        # HITL / extraction state — reset each turn
        "memory_mismatches": {},
        "pending_fields":    {},
        "response_type":     "text",
        "response_options":  [],

        # Routing defaults
        "detected_intent":   "general_chat",
        "intent_confidence": 0.0,
        "next_handler":      "handle_general",

        # Handler defaults
        "clarification_needed":   False,
        "clarification_question": None,
        "query_response":         None,

        # LLM output
        "agent_response": "",

        # Token tracking
        "total_tokens":     prior_tokens,
        "should_summarize": False,
        "summary":          None,

        "error": None,
    }

    # ── Run agent ───────────────────────────────────────────────────────────
    try:
        final_state = await run_session(initial_state)
    except Exception as e:
        logger.error(f"❌ Graph execution failed: {e}", exc_info=True)
        final_state = initial_state
        final_state["error"] = str(e)
        final_state["agent_response"] = "I encountered an internal error. Please try again."

    # ── Write updated state back to shared SESSIONS store ──────────────────
    updated_messages = final_state.get("messages", prior_messages)
    updated_tokens   = final_state.get("total_tokens", 0)
    updated_pending  = final_state.get("pending_fields") or {}

    SESSIONS[session_id]["messages"]      = updated_messages
    SESSIONS[session_id]["total_tokens"]  = updated_tokens
    SESSIONS[session_id]["pending_fields"] = updated_pending   # ← critical for confirm-save

    # ── Also persist messages to DB for durability ──────────────────────────
    try:
        with UserDatabase(db_path=SQLITE_PATH) as db:
            db.init_user_schema()   # ensure columns exist before writing
            db.save_session_messages(session_id, updated_messages)
    except Exception as db_err:
        logger.warning(f"⚠️  Could not persist messages to DB: {db_err}")

    logger.info(
        f"✅ [session/{session_id[:8]}] done | "
        f"tokens={updated_tokens} | msgs={len(updated_messages)} | "
        f"pending={list(updated_pending.keys())}"
    )

    # ─────────────────────────────────────────────────────────────────────────
    # TRANSLATE-OUT: translate English agent response → user's language
    # ─────────────────────────────────────────────────────────────────────────
    english_response  = final_state.get("agent_response", "")
    english_options   = final_state.get("response_options") or []

    if detected_lang != "en":
        final_response_text = await translate_to_user_language(
            english_response, detected_lang, translate_llm
        )
        # Audit log if Hindi translation may have silently failed
        if detected_lang == "hi" and _looks_like_english(final_response_text):
            logger.warning(
                f"⚠️  [session/{session_id[:8]}] Hindi translation may have failed — "
                f"response still looks like English. Check Ollama model capacity."
            )
        # Translate quick-reply chip labels
        if english_options:
            options_blob = "\n".join(english_options)
            translated_blob = await translate_to_user_language(
                options_blob, detected_lang, translate_llm
            )
            final_options = [line.strip() for line in translated_blob.splitlines() if line.strip()]
            if len(final_options) != len(english_options):
                final_options = english_options   # count mismatch → keep English
        else:
            final_options = english_options
    else:
        final_response_text = english_response
        final_options       = english_options

    return MessageResponse(
        success=not bool(final_state.get("error")),
        session_id=session_id,
        user_input=raw_input,
        agent_response=final_response_text,
        response_type=final_state.get("response_type", "text"),
        response_options=final_options,
        pending_fields=updated_pending or None,
        detected_intent=final_state.get("detected_intent"),
        clarification_question=final_state.get("clarification_question"),
        total_tokens=updated_tokens,
        should_summarize=final_state.get("should_summarize"),
        has_mismatch=bool(final_state.get("memory_mismatches")),
        mismatched_fields=final_state.get("memory_mismatches") or None,
        error=final_state.get("error"),
    )


@router.get("/state/{session_id}", response_model=SessionStateResponse)
async def get_session_state(session_id: str):
    """Return lightweight state for a session."""
    session = SESSIONS.get(session_id, {})
    return SessionStateResponse(
        success=True,
        session_id=session_id,
        customer_id=session.get("customer_id", "unknown"),
        state={
            "message_count": len(session.get("messages", [])),
            "total_tokens":  session.get("total_tokens", 0),
            "pending_fields": list((session.get("pending_fields") or {}).keys()),
        },
    )


@router.get("/health")
async def session_health():
    """Health check."""
    try:
        get_graph()
        return {"status": "healthy", "service": "session", "active_sessions": len(SESSIONS)}
    except Exception as e:
        return {"status": "unhealthy", "service": "session", "error": str(e)}
