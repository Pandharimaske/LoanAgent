"""
Agent Chat Routes — LangGraph integration for conversational AI

Endpoints for chatting with the loan agent.
Uses the new restructured LangGraph orchestration.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from agent.graph import build_graph
from agent.state import SessionState

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/chat", tags=["chat"])


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================

class ChatRequest(BaseModel):
    """Send message to loan agent."""
    session_id: Optional[str] = None  # Auto-generate if not provided
    customer_id: str  # Customer identifier
    user_input: str  # User message
    language: Optional[str] = "en"  # 'en' or 'hi'


class ChatResponse(BaseModel):
    """Agent chat response."""
    success: bool
    session_id: str
    customer_id: str
    user_input: str
    agent_response: str
    detected_intent: Optional[str] = None
    has_mismatch: Optional[bool] = None
    mismatched_fields: Optional[Dict[str, Any]] = None
    clarification_question: Optional[str] = None
    memory_updates: Optional[list] = None
    total_tokens: Optional[int] = None
    should_summarize: Optional[bool] = None
    error: Optional[str] = None
    timestamp: str = None


class SessionInfo(BaseModel):
    """Session information."""
    session_id: str
    customer_id: str
    created_at: str


class SessionStartRequest(BaseModel):
    """Start new session."""
    customer_id: str
    language: Optional[str] = "en"


class SessionStartResponse(BaseModel):
    """Session start response."""
    success: bool
    session_id: str
    customer_id: str
    created_at: str
    message: str


# ============================================================================
# IN-MEMORY SESSION STORE (TODO: Move to database)
# ============================================================================

SESSIONS: Dict[str, Dict[str, Any]] = {}


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Get session from store."""
    return SESSIONS.get(session_id)


def create_session(customer_id: str, language: str = "en") -> str:
    """Create new session."""
    session_id = str(uuid.uuid4())
    SESSIONS[session_id] = {
        "session_id": session_id,
        "customer_id": customer_id,
        "language": language,
        "created_at": datetime.now().isoformat(),
        "total_tokens": 0,
        "messages": [],
    }
    logger.info(f"✅ Session created: {session_id}")
    return session_id


# ============================================================================
# ROUTES
# ============================================================================

@router.post("/start", response_model=SessionStartResponse)
async def start_session(request: SessionStartRequest):
    """
    Start a new chat session.
    
    Args:
        request: Session start details with customer_id
        
    Returns:
        SessionStartResponse with new session_id
    """
    try:
        session_id = create_session(request.customer_id, request.language or "en")
        
        return SessionStartResponse(
            success=True,
            session_id=session_id,
            customer_id=request.customer_id,
            created_at=datetime.now().isoformat(),
            message=f"Session started for customer {request.customer_id}",
        )
    
    except Exception as e:
        logger.error(f"❌ Session start failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start session: {str(e)}",
        )


@router.post("/message", response_model=ChatResponse)
async def send_message(request: ChatRequest):
    """
    Send a message to the loan agent.
    
    Orchestrates through LangGraph:
    1. check_token_threshold (if over 80%, summarize)
    2. load_memory (SQLite + ChromaDB)
    3. extract_entities (parse intent & mismatches)
    4. router (decide handler)
    5. handle_* (process based on intent)
    6. end_session (persist to DB)
    
    Args:
        request: Chat message with session_id, customer_id, user_input
        
    Returns:
        ChatResponse with agent response and analysis
    """
    try:
        session_id = request.session_id or create_session(request.customer_id, request.language or "en")
        
        logger.info(f"📨 Message received | Session: {session_id} | Input: {request.user_input[:50]}...")
        
        # Initialize state for new message
        initial_state: SessionState = {
            # Session metadata
            "session_id": session_id,
            "customer_id": request.customer_id,
            "started_at": datetime.now(),
            
            # Input
            "user_input": request.user_input,
            "language": request.language or "en",
            
            # Memory (will be loaded by load_memory node)
            "confirmed_facts": {},
            "dynamic_context": [],
            "session_summaries": [],
            
            # Entity extraction (will be populated by extract_entities node)
            "extracted_entities": {},
            "detected_intent": "general_chat",
            "intent_confidence": 0.0,
            
            # Mismatch detection (will be populated by extract_entities node)
            "has_mismatch": False,
            "mismatched_fields": {},
            
            # Handler-specific (optional)
            "clarification_needed": False,
            "clarification_question": None,
            "user_confirmed_update": None,
            "memory_updates": [],
            "fields_changed": [],
            "query_type": None,
            "query_response": None,
            
            # LLM inference
            "agent_response": "",
            "model_temperature": 0.7,
            "max_tokens": 256,
            
            # Token management
            "total_tokens": 0,
            "should_summarize": False,
            "compression_ratio": 0.0,
            "summary": None,
            
            # Error & routing
            "error": None,
            "next_handler": "handle_general",
        }
        
        logger.info("🔄 Building LangGraph...")
        
        # Build and run the graph
        graph = build_graph()
        
        logger.info("🚀 Executing orchestration...")
        
        # Execute the graph asynchronously
        try:
            final_state = await graph.ainvoke(initial_state)
        except Exception as graph_error:
            logger.error(f"❌ Graph execution failed: {graph_error}")
            final_state = initial_state
            final_state["error"] = str(graph_error)
        
        logger.info(f"✅ Orchestration complete | Intent: {final_state.get('detected_intent')}")
        
        # Extract response data
        response = ChatResponse(
            success=not bool(final_state.get("error")),
            session_id=session_id,
            customer_id=request.customer_id,
            user_input=request.user_input,
            agent_response=final_state.get("agent_response", "I encountered an issue processing your request."),
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
        
        logger.info(f"📤 Response sent | Success: {response.success}")
        
        return response
    
    except Exception as e:
        logger.error(f"❌ Message processing failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}",
        )


@router.get("/session/{session_id}", response_model=SessionInfo)
async def get_session_info(session_id: str):
    """
    Get session information.
    
    Args:
        session_id: Unique session identifier
        
    Returns:
        Session metadata
    """
    try:
        session = get_session(session_id)
        
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )
        
        return SessionInfo(
            session_id=session["session_id"],
            customer_id=session["customer_id"],
            created_at=session["created_at"],
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get session info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve session: {str(e)}",
        )


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """
    End/delete a session.
    
    Args:
        session_id: Session to delete
        
    Returns:
        Success confirmation
    """
    try:
        if session_id in SESSIONS:
            del SESSIONS[session_id]
            logger.info(f"🗑️  Session deleted: {session_id}")
            return {"success": True, "message": f"Session {session_id} deleted"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session {session_id} not found",
            )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to delete session: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete session: {str(e)}",
        )


@router.get("/health")
async def chat_health():
    """Health check for chat service."""
    try:
        # Test graph compilation
        graph = build_graph()
        return {
            "status": "healthy",
            "service": "chat",
            "graph_ready": True,
            "active_sessions": len(SESSIONS),
        }
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return {
            "status": "unhealthy",
            "service": "chat",
            "error": str(e),
        }
