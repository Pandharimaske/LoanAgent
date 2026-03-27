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

    Flow:
      check_token_threshold → load_memory → extract_memory_node → router
        → handle_mismatch_confirmation | handle_query | handle_general
        → end_session
    """

    # =============================
    # SESSION METADATA
    # =============================
    session_id: str
    customer_id: str
    session_end_time: Optional[str]   # set by end_session node

    # =============================
    # INPUT
    # =============================
    user_input: str
    language: str   # 'en' / 'hi' — reserved for multilingual support

    # =============================
    # CONVERSATION HISTORY
    # =============================
    messages: List[Dict[str, str]]  # [{\"role\": \"user\"|\"assistant\", \"content\": \"...\"}, ...]

    # =============================
    # MEMORY (loaded by load_memory, refreshed by extract_memory_node)
    # =============================
    customer_facts: Dict[str, Any]      # Structured facts from SQLite, grouped by category
    dynamic_context: List[str]          # Top-K semantic chunks from ChromaDB
    session_summaries: List[str]        # Past session summaries from ChromaDB
    memory_prompt_block: Optional[str]  # Formatted 3-tier context block injected into LLMs

    # =============================
    # EXTRACTION & CONFLICT DETECTION (set by extract_memory_node)
    # =============================
    memory_mismatches: Dict[str, Dict[str, Any]]  # {field: {old_value, new_value, confidence, explanation}}

    # =============================
    # HUMAN-IN-THE-LOOP SAVE
    # =============================
    pending_fields: Dict[str, Any]    # Extracted financial facts awaiting user confirmation
    response_type: str                # "text" | "options" | "save_confirmation" | "mismatch_confirmation"
    response_options: List[str]       # Quick-reply chips to render in frontend

    # =============================
    # ROUTING (set by router node)
    # =============================
    next_handler: str        # \"handle_mismatch_confirmation\" | \"handle_query\" | \"handle_general\"
    detected_intent: str     # \"update_info (mismatch)\" | \"query_loan\" | \"general_chat\"
    intent_confidence: float
    router_reasoning: str    # LLM's reasoning for the routing decision
    router_confidence: float

    # =============================
    # HANDLER: MISMATCH CONFIRMATION
    # =============================
    clarification_needed: bool
    clarification_question: Optional[str]

    # =============================
    # HANDLER: QUERY
    # =============================
    query_response: Optional[str]

    # =============================
    # LLM OUTPUT
    # =============================
    agent_response: str   # Final response sent back to the user

    # =============================
    # TOKEN COUNT & COMPRESSION
    # =============================
    total_tokens: int
    should_summarize: bool
    summary: Optional[str]

    # =============================
    # ERROR HANDLING
    # =============================
    error: Optional[str]
