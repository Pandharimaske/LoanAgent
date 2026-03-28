"""
Agent Chat Routes — LangGraph integration for conversational AI.

FIX #5  — message history is carried forward across turns (not reset each request).
FIX #8  — graph is compiled once via get_graph() (not rebuilt per request).
FIX #10 — session messages are seeded from and persisted to user_sessions DB.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

# FIX #8 — use singleton accessor instead of build_graph()
from agent.graph import get_graph
from agent.state import SessionState
from auth.user_store import UserDatabase
from config import SQLITE_PATH

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


# ============================================================================
# REQUEST / RESPONSE SCHEMAS
# ============================================================================

class ChatRequest(BaseModel):
    session_id:  Optional[str] = None   # auto-generated if absent
    customer_id: str
    user_input:  str
    language:    Optional[str] = "en"


class ChatResponse(BaseModel):
    success:               bool
    session_id:            str
    customer_id:           str
    user_input:            str
    agent_response:        str
    # Structured UX fields (HITL + quick-replies)
    response_type:         Optional[str]             = "text"   # text | options | save_confirmation | mismatch_confirmation
    response_options:      Optional[List[str]]        = None     # quick-reply chip labels
    pending_fields:        Optional[Dict[str, Any]]  = None     # fields awaiting user confirmation
    # Metadata
    detected_intent:       Optional[str]             = None
    clarification_question: Optional[str]            = None
    total_tokens:          Optional[int]             = None
    should_summarize:      Optional[bool]            = None
    error:                 Optional[str]             = None
    timestamp:             Optional[str]             = None


class SessionStartRequest(BaseModel):
    customer_id: str
    language:    Optional[str] = "en"


class SessionStartResponse(BaseModel):
    success:     bool
    session_id:  str
    customer_id: str
    created_at:  str
    message:     str


class SessionInfo(BaseModel):
    session_id:  str
    customer_id: str
    created_at:  str


# ============================================================================
# FIX #5 — IN-MEMORY SESSION STORE
#
# Stores per-session state between HTTP requests:
#   - messages      : running conversation history (carried forward each turn)
#   - total_tokens  : cumulative token count (used by check_token_threshold)
#   - customer_id   : scoped to the auth'd customer
#   - language      : preferred language
#   - created_at    : session creation timestamp
#
# NOTE: This is in-memory; for production, move to Redis or a DB-backed store.
# ============================================================================

SESSIONS: Dict[str, Dict[str, Any]] = {}


def _get_session(session_id: str) -> Optional[Dict[str, Any]]:
    return SESSIONS.get(session_id)


def _count_tokens_approx(messages: List[Dict[str, Any]]) -> int:
    """Rough token estimate — 4 chars ≈ 1 token. Used to seed total_tokens."""
    return sum(len(m.get("content", "") or "") // 4 for m in messages)


def _create_session(customer_id: str, language: str = "en", session_id: str | None = None) -> str:
    """
    Create an in-memory session entry, seeding message history from DB if
    an existing session_id is provided (e.g. user resuming after server restart).

    If the session had previously been compressed (token threshold was hit),
    the saved summary is re-injected as a system message so context is not lost.
    """
    sid = session_id or str(uuid.uuid4())

    # FIX #10 — seed messages from DB when resuming an existing session
    prior_messages: List[Dict[str, Any]] = []
    prior_summary: str | None = None
    if session_id:
        try:
            with UserDatabase(db_path=SQLITE_PATH) as db:
                prior_messages = db.get_session_messages(session_id)
                prior_summary  = db.get_session_summary(session_id)
        except Exception as e:
            logger.warning(f"⚠️  Could not load prior messages/summary from DB: {e}")

    # If a summary was saved (token compression happened) and the first message
    # in history is NOT already a system summary, prepend one so the LLM has
    # a compact recap without re-loading the full (possibly trimmed) history.
    if prior_summary:
        has_summary_msg = any(
            m.get("role") == "system" and "[Earlier conversation summary]" in m.get("content", "")
            for m in prior_messages
        )
        if not has_summary_msg:
            logger.info(f"📋 Re-injecting session summary into resumed context for {sid[:8]}")
            prior_messages = [{
                "role": "system",
                "content": f"[Earlier conversation summary]: {prior_summary}",
                "timestamp": datetime.now().isoformat(),
            }] + prior_messages

    SESSIONS[sid] = {
        "session_id":   sid,
        "customer_id":  customer_id,
        "language":     language,
        "created_at":   datetime.now().isoformat(),
        "messages":     prior_messages,          # seeded from DB (or [] for brand-new)
        "total_tokens": _count_tokens_approx(prior_messages),  # recalculate
    }
    logger.info(
        f"✅ Session created: {sid} for {customer_id} "
        f"| {len(prior_messages)} prior messages loaded"
        + (f" | summary re-injected" if prior_summary else "")
    )
    return sid


# ============================================================================
# ROUTES
# ============================================================================

@router.post("/start", response_model=SessionStartResponse)
async def start_session(request: SessionStartRequest):
    """Create a new chat session and return its ID."""
    try:
        session_id = _create_session(request.customer_id, request.language or "en")
        return SessionStartResponse(
            success=True,
            session_id=session_id,
            customer_id=request.customer_id,
            created_at=datetime.now().isoformat(),
            message=f"Session started for customer {request.customer_id}",
        )
    except Exception as e:
        logger.error(f"❌ start_session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """
    Send a message to the loan agent.

    Key changes vs old version:
    - FIX #5: prior messages are loaded from session store into initial_state
              and saved back after the graph completes.
    - FIX #6: total_tokens is carried forward so check_token_threshold works.
    - FIX #8: graph compiled once; get_graph() returns cached instance.
    """
    try:
        # Resolve or create session
        # FIX #10 — if session_id provided but not in memory (e.g. server restart),
        #           re-create the in-memory entry, seeding from DB.
        session_id = request.session_id
        if not session_id:
            session_id = _create_session(request.customer_id, request.language or "en")
        elif session_id not in SESSIONS:
            session_id = _create_session(
                request.customer_id,
                request.language or "en",
                session_id=session_id,   # ← seed from DB
            )

        session_data = SESSIONS[session_id]
        language = session_data.get("language", request.language or "en")

        logger.info(f"📨 [{session_id[:8]}] '{request.user_input[:60]}…'")

        # ------------------------------------------------------------------
        # FIX #5 — carry messages and token count forward from session store
        # ------------------------------------------------------------------
        prior_messages:     List[Dict[str, Any]] = list(session_data.get("messages", []))
        prior_token_count:  int                  = session_data.get("total_tokens", 0)

        # ------------------------------------------------------------------
        # Build initial state
        # ------------------------------------------------------------------
        initial_state: SessionState = {
            # Session metadata
            "session_id":  session_id,
            "customer_id": request.customer_id,

            # Input
            "user_input": request.user_input,
            "language":   language,

            # Carry forward prior messages
            "messages": prior_messages,

            # Memory (populated by load_memory)
            "customer_facts":      {},
            "dynamic_context":     [],
            "session_summaries":   [],
            "memory_prompt_block": None,

            # Extraction + HITL
            "memory_mismatches":  {},
            "pending_fields":     {},
            "response_type":      "text",
            "response_options":   [],

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
            "total_tokens":     prior_token_count,
            "should_summarize": False,
            "summary":          None,

            # Error
            "error": None,
        }

        # ------------------------------------------------------------------
        # FIX #8 — use cached graph (compiled once at module level)
        # ------------------------------------------------------------------
        graph = get_graph()

        try:
            final_state = await graph.ainvoke(initial_state)
        except Exception as graph_error:
            logger.error(f"❌ Graph execution failed: {graph_error}", exc_info=True)
            final_state = initial_state
            final_state["error"] = str(graph_error)
            final_state["agent_response"] = "I encountered an internal error. Please try again."

        # ------------------------------------------------------------------
        # FIX #5  — persist updated messages + token count back to in-memory store
        # FIX #10 — also write messages back to user_sessions DB for durability
        # ------------------------------------------------------------------
        updated_messages = final_state.get("messages", prior_messages)
        updated_tokens   = final_state.get("total_tokens", 0)

        SESSIONS[session_id]["messages"]      = updated_messages
        SESSIONS[session_id]["total_tokens"]  = updated_tokens
        # Persist pending_fields so /confirm-save can read them
        SESSIONS[session_id]["pending_fields"] = final_state.get("pending_fields") or {}

        # Persist to DB (non-fatal if it fails)
        try:
            with UserDatabase(db_path=SQLITE_PATH) as db:
                db.save_session_messages(session_id, updated_messages)
        except Exception as db_err:
            logger.warning(f"⚠️  Could not persist messages to DB: {db_err}")

        logger.info(
            f"✅ [{session_id[:8]}] done | "
            f"tokens={updated_tokens} | "
            f"msgs={len(updated_messages)}"
        )

        return ChatResponse(
            success=not bool(final_state.get("error")),
            session_id=session_id,
            customer_id=request.customer_id,
            user_input=request.user_input,
            agent_response=final_state.get(
                "agent_response", "I encountered an issue processing your request."
            ),
            response_type=final_state.get("response_type", "text"),
            response_options=final_state.get("response_options") or [],
            pending_fields=final_state.get("pending_fields") or None,
            detected_intent=final_state.get("detected_intent"),
            clarification_question=final_state.get("clarification_question"),
            total_tokens=final_state.get("total_tokens"),
            should_summarize=final_state.get("should_summarize"),
            error=final_state.get("error"),
            timestamp=datetime.now().isoformat(),
        )

    except Exception as e:
        logger.error(f"❌ send_message crashed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/session/{session_id}", response_model=SessionInfo)
async def get_session_info(session_id: str):
    """Return metadata for an active session."""
    session = _get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return SessionInfo(
        session_id=session["session_id"],
        customer_id=session["customer_id"],
        created_at=session["created_at"],
    )


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Terminate and remove a session."""
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    del SESSIONS[session_id]
    logger.info(f"🗑️  Session deleted: {session_id}")
    return {"success": True, "message": f"Session {session_id} deleted"}


# ============================================================================
# HUMAN-IN-THE-LOOP: CONFIRM SAVE
# ============================================================================

class ConfirmSaveRequest(BaseModel):
    customer_id:   str
    session_id:    str
    approved:      bool                          # True = save, False = discard
    edited_fields: Optional[Dict[str, Any]] = None  # User-corrected values


class ConfirmSaveResponse(BaseModel):
    success:       bool
    status:        str                          # "saved" | "discarded"
    fields_written: Optional[List[str]] = None
    response:      str
    error:         Optional[str] = None


@router.post("/confirm-save", response_model=ConfirmSaveResponse)
async def confirm_save(request: ConfirmSaveRequest):
    """
    Human-in-the-loop memory save endpoint.

    When the agent extracts financial facts and puts them in pending_fields,
    the frontend renders a SaveConfirmationCard. The user confirms, edits,
    or discards. This endpoint executes the final write (or discard).
    """
    try:
        if not request.approved:
            logger.info(f"🚫 User discarded pending fields for {request.customer_id}")
            return ConfirmSaveResponse(
                success=True,
                status="discarded",
                response="No problem! I won't save those details.",
            )

        # Retrieve pending_fields from in-memory session
        session = SESSIONS.get(request.session_id)
        pending: Dict[str, Any] = {}

        if session:
            pending = session.get("pending_fields", {})

        # Allow user-edited overrides
        if request.edited_fields:
            pending.update(request.edited_fields)

        if not pending:
            logger.warning(
                f"confirm-save: no pending_fields found for session {request.session_id}. "
                f"SESSIONS keys: {list(SESSIONS.keys())[:5]}"
            )
            return ConfirmSaveResponse(
                success=True,
                status="discarded",
                response="Nothing to save — the fields may have already been cleared.",
            )

        # Resolve the real customer_id from the session store
        # (frontend may send 'Not assigned' or the session_id as a fallback)
        customer_id = request.customer_id
        if session and session.get("customer_id"):
            customer_id = session["customer_id"]

        # Write to SQLite
        from memory.sqlite_store import MemoryDatabase
        with MemoryDatabase(db_path=SQLITE_PATH) as db:
            db.init_schema()
            db.batch_update_fields(customer_id=customer_id, fields=pending)

        # Clear pending_fields from session
        if session:
            session["pending_fields"] = {}

        fields_written = list(pending.keys())
        logger.info(f"✅ Confirmed save for {customer_id}: {fields_written}")

        return ConfirmSaveResponse(
            success=True,
            status="saved",
            fields_written=fields_written,
            response=f"Got it! I've saved your updated details ({', '.join(fields_written).replace('_', ' ')}).",
        )

    except Exception as e:
        logger.error(f"❌ confirm_save failed: {e}", exc_info=True)
        return ConfirmSaveResponse(
            success=False,
            status="error",
            response="Something went wrong saving your data. Please try again.",
            error=str(e),
        )


@router.get("/health")
async def chat_health():
    """Health check — verifies the graph compiles without error."""
    try:
        graph = get_graph()
        return {
            "status":          "healthy",
            "service":         "chat",
            "graph_ready":     True,
            "active_sessions": len(SESSIONS),
        }
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return {"status": "unhealthy", "service": "chat", "error": str(e)}
