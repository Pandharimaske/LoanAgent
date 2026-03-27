"""
Agent Chat Routes — LangGraph integration for conversational AI.

FIX #5  — message history is carried forward across turns (not reset each request).
FIX #8  — graph is compiled once via get_graph() (not rebuilt per request).
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
    detected_intent:       Optional[str]         = None
    has_mismatch:          Optional[bool]        = None
    mismatched_fields:     Optional[Dict[str, Any]] = None
    clarification_question: Optional[str]        = None
    memory_updates:        Optional[List]        = None
    total_tokens:          Optional[int]         = None
    should_summarize:      Optional[bool]        = None
    error:                 Optional[str]         = None
    timestamp:             Optional[str]         = None


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


def _create_session(customer_id: str, language: str = "en") -> str:
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "session_id":   session_id,
        "customer_id":  customer_id,
        "language":     language,
        "created_at":   datetime.now().isoformat(),
        "messages":     [],           # FIX #5 — persistent message buffer
        "total_tokens": 0,            # FIX #6 — carries token count across turns
    }
    logger.info(f"✅ Session created: {session_id} for {customer_id}")
    return session_id


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
        session_id = request.session_id
        if not session_id or session_id not in SESSIONS:
            session_id = _create_session(request.customer_id, request.language or "en")
        
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
            "started_at":  datetime.now(),

            # Input
            "user_input": request.user_input,
            "language":   language,

            # FIX #5 — inject prior messages (load_memory will NOT reset these)
            "messages": prior_messages,

            # Memory (loaded by load_memory node)
            "confirmed_facts":   {},
            "dynamic_context":   [],
            "session_summaries": [],

            # Entity extraction
            "extracted_entities": {},
            "detected_intent":    "general_chat",
            "intent_confidence":  0.0,

            # Mismatch detection
            "has_mismatch":      False,
            "mismatched_fields": {},

            # Handler-specific
            "clarification_needed":  False,
            "clarification_question": None,
            "user_confirmed_update": None,
            "memory_updates":        [],
            "fields_changed":        [],
            "query_type":            None,
            "query_response":        None,

            # LLM inference
            "agent_response":   "",
            "model_temperature": 0.7,
            "max_tokens":        256,

            # FIX #6 — carry token count forward
            "total_tokens":     prior_token_count,
            "should_summarize": False,
            "compression_ratio": 0.0,
            "summary":          None,

            # Error & routing
            "error":        None,
            "next_handler": "handle_general",
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
        # FIX #5 — persist updated messages + token count back to session store
        # ------------------------------------------------------------------
        SESSIONS[session_id]["messages"]     = final_state.get("messages", prior_messages)
        SESSIONS[session_id]["total_tokens"] = final_state.get("total_tokens", 0)

        logger.info(
            f"✅ [{session_id[:8]}] done | "
            f"tokens={final_state.get('total_tokens',0)} | "
            f"msgs={len(SESSIONS[session_id]['messages'])}"
        )

        return ChatResponse(
            success=not bool(final_state.get("error")),
            session_id=session_id,
            customer_id=request.customer_id,
            user_input=request.user_input,
            agent_response=final_state.get(
                "agent_response", "I encountered an issue processing your request."
            ),
            detected_intent=final_state.get("detected_intent"),
            has_mismatch=final_state.get("has_mismatch"),
            mismatched_fields=final_state.get("mismatched_fields"),
            clarification_question=final_state.get("clarification_question"),
            memory_updates=final_state.get("memory_updates"),
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
