"""
Session orchestration routes.

Endpoints for starting sessions, sending messages, and retrieving session state.
Uses LangGraph for agent orchestration.
"""

from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, EmailStr
from typing import Optional, Dict, Any
from datetime import datetime
import uuid

from agent.graph import run_session
from agent.state import SessionState
from auth.user_store import UserDatabase
from config import SQLITE_PATH

# Create router
router = APIRouter(prefix="/session", tags=["session"])

# Dependency to get database
def get_db():
    """Get database connection."""
    db = UserDatabase(db_path=SQLITE_PATH)
    db.connect()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# REQUEST/RESPONSE SCHEMAS
# ============================================================================

class SessionStartRequest(BaseModel):
    """Start a new session request."""
    session_id: Optional[str] = None  # Auto-generate if not provided
    customer_id: str
    language: Optional[str] = "en"  # 'en' or 'hi'


class SessionStartResponse(BaseModel):
    """Session start response."""
    success: bool
    session_id: str
    customer_id: str
    started_at: str
    message: str


class MessageRequest(BaseModel):
    """Send message to agent."""
    session_id: str
    user_input: str
    language: Optional[str] = "en"


class MessageResponse(BaseModel):
    """Agent response message."""
    success: bool
    session_id: str
    user_input: str
    agent_response: str
    detected_conflicts: Optional[list] = None
    clarification_question: Optional[str] = None
    memory_updates: Optional[list] = None
    error: Optional[str] = None


class SessionStateResponse(BaseModel):
    """Full session state."""
    success: bool
    session_id: str
    customer_id: str
    state: Dict[str, Any]


# ============================================================================
# ROUTES
# ============================================================================

@router.post("/start", response_model=SessionStartResponse)
async def start_session(request: SessionStartRequest):
    """
    Start a new session.
    
    Args:
        request: Session start details
        
    Returns:
        SessionStartResponse with session_id
    """
    try:
        session_id = request.session_id or str(uuid.uuid4())
        customer_id = request.customer_id
        language = request.language or "en"
        now = datetime.now()
        
        return SessionStartResponse(
            success=True,
            session_id=session_id,
            customer_id=customer_id,
            started_at=now.isoformat(),
            message=f"Session {session_id} started for customer {customer_id}",
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start session: {str(e)}",
        )


@router.post("/message", response_model=MessageResponse)
async def send_message(request: MessageRequest):
    """
    Send a message to the loan agent.
    Runs the LangGraph workflow to process the message.
    
    Args:
        request: Message with session_id and user_input
        
    Returns:
        MessageResponse with agent response and state updates
    """
    try:
        # Resolve real customer_id from the authenticated session
        customer_id = "demo_customer"  # last-resort fallback
        try:
            import hashlib
            db = UserDatabase(db_path=SQLITE_PATH)
            db.connect()
            user_session = db.get_session(request.session_id)
            if user_session and user_session.customer_id:
                # Happy path: customer_id stored at registration
                customer_id = user_session.customer_id
            elif user_session:
                # Legacy user registered before the customer_id fix.
                # Re-derive the same deterministic CUST_ id from email so the
                # data bucket is consistent with any future registrations.
                user = db.get_user(user_session.user_id)
                if user and user.email:
                    customer_id = "CUST_" + hashlib.sha256(user.email.lower().encode()).hexdigest()[:8].upper()
                else:
                    customer_id = f"CUST_{user_session.user_id[-8:].upper()}"
            db.close()
        except Exception:
            pass  # keep fallback

        # Initialize state
        initial_state: SessionState = {
            "session_id": request.session_id,
            "customer_id": customer_id,
            "user_input": request.user_input,
            "language": request.language,
            "started_at": datetime.now(),
            
            # Memory (empty for now, will be loaded by load_memory node)
            "confirmed_facts": {},
            "dynamic_context": [],
            "session_summaries": [],
            
            # Extraction (will be populated)
            "extracted_entities": {},
            
            # Conflict detection (will be populated)
            "detected_conflicts": [],
            "conflict_detected": False,
            
            # Clarification (optional)
            "clarification_question": None,
            "user_clarified": True,
            
            # Inference (will be populated)
            "agent_response": "",
            "model_temperature": 0.7,
            "max_tokens": 256,
            
            # Tokens (will be populated)
            "total_tokens": 0,
            "should_summarize": False,
            "compression_ratio": 0.0,
            "summary": None,
            
            # Updates (will be populated)
            "memory_updates": [],
            "fields_changed": [],
            
            # Error/routing
            "error": None,
            "next_node": None,
        }
        
        # Run through LangGraph
        import asyncio
        final_state = await run_session(initial_state)
        
        return MessageResponse(
            success=not bool(final_state.get("error")),
            session_id=request.session_id,
            user_input=request.user_input,
            agent_response=final_state.get("agent_response", ""),
            detected_conflicts=final_state.get("detected_conflicts"),
            clarification_question=final_state.get("clarification_question"),
            memory_updates=final_state.get("memory_updates"),
            error=final_state.get("error"),
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process message: {str(e)}",
        )


@router.get("/state/{session_id}", response_model=SessionStateResponse)
async def get_session_state(session_id: str):
    """
    Get the current state of a session.
    
    Args:
        session_id: Session ID
        
    Returns:
        Current session state
    """
    try:
        # TODO: Retrieve from session store/database
        return SessionStateResponse(
            success=True,
            session_id=session_id,
            customer_id="demo_customer",
            state={},
        )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve session state: {str(e)}",
        )
