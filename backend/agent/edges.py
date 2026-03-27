"""
LangGraph Edge Definitions — Conditional routing between nodes.

New Restructured Flow:
1. check_token_threshold (FIRST)
2. load_memory
3. extract_entities
4. router (decides next handler)
5. handle_memory_update | handle_query | handle_general
6. end_session
"""

from agent.state import SessionState


# ============================================================================
# CONDITIONAL EDGE FUNCTION
# ============================================================================

def route_to_handler(state: SessionState) -> str:
    """
    Router decides which handler to invoke based on state.
    
    Logic:
    - If has_mismatch=True → "handle_memory_update"
    - Else if detected_intent in [query_loan, ask_status] → "handle_query"
    - Else → "handle_general"
    
    Returns:
        Handler node name
    """
    next_handler = state.get("next_handler", "handle_general")
    return next_handler


# ============================================================================
# EDGE DEFINITIONS (exported as list for graph builder)
# ============================================================================

CONDITIONAL_EDGES = [
    # (source_node, conditional_function, {"option1": "target1", ...})
    (
        "router",
        route_to_handler,
        {
            "handle_memory_update": "handle_memory_update",
            "handle_query": "handle_query",
            "handle_general": "handle_general",
        }
    )
]
