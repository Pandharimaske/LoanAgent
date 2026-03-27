"""
LangGraph Edge Definitions — Conditional routing between nodes.

Edges define the flow:
- Always-on edges: linear progression
- Conditional edges: branching based on state
"""

from agent.state import SessionState


# ============================================================================
# CONDITIONAL EDGE FUNCTIONS
# ============================================================================

def route_after_conflict_detection(state: SessionState) -> str:
    """
    Decide whether to ask user for clarification or proceed to update memory.
    
    Returns:
        "ask_user" if conflicts detected
        "retrieve_context" to skip clarification and proceed
    """
    conflict_detected = state.get("conflict_detected", False)
    
    if conflict_detected:
        return "ask_user"
    else:
        return "retrieve_context"


def route_after_ask_user(state: SessionState) -> str:
    """
    After asking user, wait for clarification or skip if no conflicts.
    
    In production, this would check if user_clarification has been filled.
    For now, assume user clarified and proceed.
    
    Returns:
        "retrieve_context" to continue to inference
    """
    return "retrieve_context"


def route_after_inference(state: SessionState) -> str:
    """
    After LLM inference, decide whether to compress or end.
    
    Returns:
        "check_token_threshold" always (we always check)
    """
    return "check_token_threshold"


def route_after_threshold_check(state: SessionState) -> str:
    """
    Decide whether to summarize conversation or end session.
    
    Returns:
        "end_session" always (persist happens either way)
    """
    # In production, could do separate "summarize" node here
    # For now, just end (summary logic in end_session)
    return "end_session"


# ============================================================================
# EDGE DEFINITIONS (exported as list for graph builder)
# ============================================================================

CONDITIONAL_EDGES = [
    # (source_node, conditional_function, {"option1": "target1", "option2": "target2"})
    (
        "detect_conflicts",
        route_after_conflict_detection,
        {
            "ask_user": "ask_user",
            "retrieve_context": "retrieve_context",
        }
    ),
    (
        "ask_user",
        route_after_ask_user,
        {
            "retrieve_context": "retrieve_context",
        }
    ),
    (
        "slm_inference",
        route_after_inference,
        {
            "check_token_threshold": "check_token_threshold",
        }
    ),
    (
        "check_token_threshold",
        route_after_threshold_check,
        {
            "end_session": "end_session",
        }
    ),
]

# Linear edges (source -> target, no conditions)
LINEAR_EDGES = [
    ("load_memory", "extract_entities"),
    ("extract_entities", "detect_conflicts"),
    ("retrieve_context", "slm_inference"),
]
