"""
LangGraph State Machine — SessionState definition.

Represents the complete state flowing through the agent orchestration.
All node functions read from and write to this state.
"""

from typing import TypedDict, Optional, List, Dict, Any
from datetime import datetime


class SessionState(TypedDict, total=False):
    """
    Complete session state for LoanAgent orchestration.
    
    Router Node decides the flow based on:
    - detect_intent: What is user asking? (update_info, query_loan, general_chat)
    - has_mismatch: Any conflicts between extracted and confirmed facts?
    
    Then routes to appropriate handler:
    - handle_memory_update: User provided new/conflicting info
    - handle_query: User asking questions about loan/status
    - handle_general: General conversation/clarification
    """
    
    # =============================
    # SESSION METADATA
    # =============================
    session_id: str
    customer_id: str  # Single ID - represents the customer
    started_at: datetime
    
    # =============================
    # INPUT
    # =============================
    user_input: str
    language: str  # 'en' or 'hi'
    
    # =============================
    # CONVERSATION HISTORY (Message Buffer)
    # =============================
    messages: List[Dict[str, str]]  # Conversation history: [{"role": "user"|"assistant", "content": "..."}, ...]
    
    # =============================
    # MEMORY TIER 1 & 2 (loaded in load_memory node)
    # =============================
    confirmed_facts: Dict[str, Any]  # From SQLite (monthly_income, cibil_score, etc.)
    dynamic_context: List[str]  # Top-K semantic matches from ChromaDB
    session_summaries: List[str]  # Chronological session summaries from ChromaDB
    
    # =============================
    # ENTITY EXTRACTION & INTENT DETECTION
    # =============================
    extracted_entities: Dict[str, Any]  # Newly extracted structured data from user input
    detected_intent: str  # 'update_info', 'query_loan', 'general_chat', 'ask_application_status'
    intent_confidence: float  # 0.0-1.0
    
    # =============================
    # CONFLICT/MISMATCH DETECTION (done in extract_entities)
    # =============================
    has_mismatch: bool  # True if extracted differs from confirmed
    mismatched_fields: Dict[str, Dict[str, Any]]  # {field: {existing, new, confidence}}
    
    # =============================
    # HANDLER-SPECIFIC: MEMORY UPDATES
    # =============================
    clarification_needed: bool  # True if mismatch needs user confirmation
    clarification_question: Optional[str]  # Question to ask user
    user_confirmed_update: Optional[bool]  # True if user confirmed the update
    memory_updates: List[Dict[str, Any]]  # Updates to persist
    fields_changed: List[str]
    
    # =============================
    # HANDLER-SPECIFIC: QUERY RESPONSES
    # =============================
    query_type: Optional[str]  # 'loan_info', 'application_status', 'documents'
    query_response: Optional[str]  # Answer to user's query
    
    # =============================
    # LLM INFERENCE (handler output)
    # =============================
    agent_response: str  # Final conversational response from SLM
    model_temperature: float  # Default 0.7
    max_tokens: int  # Default 256
    
    # =============================
    # TOKEN COUNT & COMPRESSION
    # =============================
    total_tokens: int  # Current conversation token count
    should_summarize: bool  # True if token threshold exceeded
    compression_ratio: float  # Current compression ratio (0.0-1.0)
    summary: Optional[str]  # Generated summary if should_summarize=True
    
    # =============================
    # ERROR & ROUTING
    # =============================
    error: Optional[str]  # Error message if any node fails
    next_handler: str  # Router decision: "memory_update", "query", "general"

