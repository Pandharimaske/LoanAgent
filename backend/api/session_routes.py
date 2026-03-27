"""
Session orchestration routes.

FIX #9  — All initial_state field names now match SessionState exactly.
           Removed stale fields: detected_conflicts, conflict_detected,
           user_clarified, next_node.
FIX #10 — Messages loaded from user_sessions DB before each turn;
           persisted back to DB after each turn.
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from agent.graph import run_session, get_graph
from agent.state import SessionState
from auth.user_store import UserDatabase
from config import SQLITE_PATH

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/session", tags=["session"])


def _count_tokens_approx(messages: List[Dict[str, Any]]) -> int:
    """Rough token estimate — 4 chars ≈ 1 token."""
    return sum(len(m.get("content", "") or "") // 4 for m in messages)


# ============================================================================
# REQUEST / RESPONSE SCHEMAS
# ============================================================================

class SessionStartRequest(BaseModel):
    session_id:  Optional[str] = None
    customer_id: str
    language:    Optional[str] = "en"


class SessionStartResponse(BaseModel):
    success:    bool
    session_id: str
    customer_id: str
    started_at: str
    message:    str


class MessageRequest(BaseModel):
    session_id: str
    user_input: str
    language:   Optional[str] = "en"


class MessageResponse(BaseModel):
    success:               bool
    session_id:            str
    user_input:            str
    agent_response:        str
    has_mismatch:          Optional[bool]          = None
    mismatched_fields:     Optional[Dict[str, Any]] = None
    clarification_question: Optional[str]          = None
    memory_updates:        Optional[list]          = None
    error:                 Optional[str]           = None


class SessionStateResponse(BaseModel):
    success:     bool
    session_id:  str
    customer_id: str
    state:       Dict[str, Any]


# ============================================================================
# ROUTES
# ============================================================================

@router.post("/start", response_model=SessionStartResponse)
async def start_session(request: SessionStartRequest):
    """Start a new session and return its ID."""
    try:
        session_id  = request.session_id or str(uuid.uuid4())
        customer_id = request.customer_id
        language    = request.language or "en"
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
    Send a message through the LangGraph workflow.

    FIX #9 — initial_state uses correct SessionState field names only.
    """
    # ------------------------------------------------------------------
    # Resolve customer_id from the auth session stored in the DB
    # ------------------------------------------------------------------
    customer_id = "demo_customer"
    try:
        with UserDatabase(db_path=SQLITE_PATH) as db:
            user_session = db.get_session(request.session_id)
            if user_session and user_session.customer_id:
                customer_id = user_session.customer_id
            elif user_session:
                # Legacy user: re-derive deterministic CUST_ id from email
                user = db.get_user(user_session.user_id)
                if user and user.email:
                    customer_id = (
                        "CUST_"
                        + hashlib.sha256(user.email.lower().encode()).hexdigest()[:8].upper()
                    )
                else:
                    customer_id = f"CUST_{user_session.user_id[-8:].upper()}"
    except Exception as e:
        logger.warning(f"⚠️  Could not resolve customer_id from session: {e}")

    # ------------------------------------------------------------------
    # FIX #10 — Load prior messages from user_sessions DB
    # This ensures message history survives across turns and server restarts.
    # ------------------------------------------------------------------
    prior_messages: List[Dict[str, Any]] = []
    try:
        with UserDatabase(db_path=SQLITE_PATH) as db:
            prior_messages = db.get_session_messages(request.session_id)
    except Exception as e:
        logger.warning(f"⚠️  Could not load prior messages from DB: {e}")

    # ------------------------------------------------------------------
    # FIX #9 — Build initial state with CORRECT SessionState field names
    # FIX #10 — Inject prior messages and recalculated token count
    # ------------------------------------------------------------------
    initial_state: SessionState = {
        # Session metadata
        "session_id":  request.session_id,
        "customer_id": customer_id,
        "started_at":  datetime.now(),

        # Input
        "user_input": request.user_input,
        "language":   request.language or "en",

        # FIX #10 — carry prior messages forward (load_memory will append current turn)
        "messages": prior_messages,

        # Memory (loaded by load_memory node)
        "customer_facts":    {},
        "dynamic_context":   [],
        "session_summaries": [],
        "memory_prompt_block": None,

        # Entity extraction
        "extracted_entities": {},
        "detected_intent":    "general_chat",
        "intent_confidence":  0.0,

        # FIX #9 — correct field names (was: conflict_detected, detected_conflicts)
        "has_mismatch":      False,
        "mismatched_fields": {},

        # Handler-specific
        "clarification_needed":  False,
        "clarification_question": None,
        # FIX #9 — correct field name (was: user_clarified)
        "user_confirmed_update": None,
        "memory_updates":        [],
        "fields_changed":        [],
        "query_type":            None,
        "query_response":        None,

        # LLM inference
        "agent_response":    "",
        "model_temperature": 0.7,
        "max_tokens":        256,

        # FIX #10 — seed token count from prior messages
        "total_tokens":     _count_tokens_approx(prior_messages),
        "should_summarize": False,
        "compression_ratio": 0.0,
        "summary":          None,

        # Error & routing — FIX #9: was "next_node", correct name is "next_handler"
        "error":        None,
        "next_handler": "handle_general",
    }

    try:
        final_state = await run_session(initial_state)

        # FIX #10 — persist updated messages back to DB after every graph turn
        updated_messages = final_state.get("messages", prior_messages)
        try:
            with UserDatabase(db_path=SQLITE_PATH) as db:
                db.save_session_messages(request.session_id, updated_messages)
        except Exception as db_err:
            logger.warning(f"⚠️  Could not persist messages to DB: {db_err}")

        return MessageResponse(
            success=not bool(final_state.get("error")),
            session_id=request.session_id,
            user_input=request.user_input,
            agent_response=final_state.get("agent_response", ""),
            has_mismatch=final_state.get("has_mismatch"),
            mismatched_fields=final_state.get("mismatched_fields"),
            clarification_question=final_state.get("clarification_question"),
            memory_updates=final_state.get("memory_updates"),
            error=final_state.get("error"),
        )
    except Exception as e:
        logger.error(f"❌ session send_message failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to process message: {e}")


@router.get("/state/{session_id}", response_model=SessionStateResponse)
async def get_session_state(session_id: str):
    """Return current state for a session (stub — extend with DB-backed store as needed)."""
    return SessionStateResponse(
        success=True,
        session_id=session_id,
        customer_id="unknown",
        state={},
    )


@router.get("/health")
async def session_health():
    """Health check for session service."""
    try:
        get_graph()   # verify graph compiles
        return {"status": "healthy", "service": "session"}
    except Exception as e:
        return {"status": "unhealthy", "service": "session", "error": str(e)}
