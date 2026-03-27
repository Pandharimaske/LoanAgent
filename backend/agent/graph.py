"""
LangGraph Workflow — Main graph compilation and execution.

Orchestrates all nodes and edges into a single executable graph.
Entry point for session processing.
"""

import sys
import logging
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent.parent))

from langgraph.graph import StateGraph, END
from agent.state import SessionState
from agent.nodes import (
    load_memory,
    extract_entities,
    detect_conflicts,
    ask_user,
    retrieve_context,
    slm_inference,
    check_token_threshold,
    end_session,
)
from agent.edges import CONDITIONAL_EDGES, LINEAR_EDGES

logger = logging.getLogger(__name__)


def build_graph():
    """
    Build and return the compiled LangGraph workflow.
    
    Returns:
        Compiled graph ready for execution
    """
    
    # Initialize graph builder
    graph = StateGraph(SessionState)
    
    # ========================================================================
    # ADD NODES
    # ========================================================================
    
    logger.info("Adding nodes to graph...")
    
    graph.add_node("load_memory", load_memory)
    graph.add_node("extract_entities", extract_entities)
    graph.add_node("detect_conflicts", detect_conflicts)
    graph.add_node("ask_user", ask_user)
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("slm_inference", slm_inference)
    graph.add_node("check_token_threshold", check_token_threshold)
    graph.add_node("end_session", end_session)
    
    logger.info("✅ Added 8 nodes")
    
    # ========================================================================
    # ADD LINEAR EDGES
    # ========================================================================
    
    logger.info("Adding linear edges...")
    
    for source, target in LINEAR_EDGES:
        graph.add_edge(source, target)
    
    logger.info(f"✅ Added {len(LINEAR_EDGES)} linear edges")
    
    # ========================================================================
    # ADD CONDITIONAL EDGES
    # ========================================================================
    
    logger.info("Adding conditional edges...")
    
    for source, condition_func, options in CONDITIONAL_EDGES:
        graph.add_conditional_edges(source, condition_func, options)
    
    logger.info(f"✅ Added {len(CONDITIONAL_EDGES)} conditional edges")
    
    # ========================================================================
    # SET ENTRY POINT & EXIT POINT
    # ========================================================================
    
    graph.set_entry_point("load_memory")
    graph.set_finish_point("end_session")
    
    logger.info("Entry: load_memory | Exit: end_session")
    
    # ========================================================================
    # COMPILE
    # ========================================================================
    
    compiled_graph = graph.compile()
    logger.info("✅ Graph compiled and ready for execution")
    
    return compiled_graph


# Global graph instance (lazy-loaded)
_graph_instance: Optional[object] = None


def get_graph():
    """
    Get or create the global compiled graph.
    
    Returns:
        Compiled LangGraph workflow
    """
    global _graph_instance
    
    if _graph_instance is None:
        _graph_instance = build_graph()
    
    return _graph_instance


async def run_session(initial_state: SessionState) -> SessionState:
    """
    Execute a complete session through the graph.
    
    Args:
        initial_state: SessionState with session_id, customer_id, user_input, etc.
        
    Returns:
        Final SessionState after all nodes executed
    """
    
    try:
        graph = get_graph()
        
        logger.info(f"🚀 Running session: {initial_state.get('session_id')}")
        
        # Stream execution for debugging
        final_state = initial_state.copy()
        
        # Execute graph (invoke returns final state)
        # For async compatibility, we'll use sync mode for now
        # In production, use graph.invoke() or astream()
        result = graph.invoke(initial_state)
        
        logger.info(f"✅ Session complete: {result.get('session_id')}")
        
        # Check for errors
        if result.get("error"):
            logger.error(f"❌ Session error: {result.get('error')}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Session execution failed: {str(e)}")
        initial_state["error"] = f"Session execution failed: {str(e)}"
        return initial_state


# ============================================================================
# DEBUG: Print graph structure
# ============================================================================

if __name__ == "__main__":
    import json
    
    logging.basicConfig(level=logging.INFO)
    
    print("\n" + "=" * 70)
    print("LoanAgent LangGraph Workflow")
    print("=" * 70 + "\n")
    
    graph = build_graph()
    
    # Print graph structure
    print("Graph Structure:")
    print("-" * 70)
    print(json.dumps(graph.schema, indent=2))
    print("-" * 70)
    
    print("\n✅ Graph ready for execution\n")
