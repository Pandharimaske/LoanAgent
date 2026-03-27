#!/usr/bin/env python3
"""
Integration test for agent chat routes and LangGraph orchestration.
Tests the complete flow: start session → send message → process through graph.
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from api.chat_routes import (
    create_session, 
    get_session, 
    ChatRequest,
    ChatResponse,
)
from agent.graph import build_graph
from agent.state import SessionState

# Color output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def test_graph_compilation():
    """Test that LangGraph compiles correctly."""
    print(f"\n{YELLOW}[1/4] Testing LangGraph Compilation...{RESET}")
    try:
        graph = build_graph()
        print(f"{GREEN}✅ Graph compiled successfully{RESET}")
        return True
    except Exception as e:
        print(f"{RED}❌ Graph compilation failed: {e}{RESET}")
        return False


def test_session_management():
    """Test session creation and retrieval."""
    print(f"\n{YELLOW}[2/4] Testing Session Management...{RESET}")
    try:
        customer_id = "test_customer_001"
        session_id = create_session(customer_id, language="en")
        
        print(f"{GREEN}✅ Session created: {session_id}{RESET}")
        
        session = get_session(session_id)
        if session:
            print(f"{GREEN}✅ Session retrieved successfully{RESET}")
            print(f"   - customer_id: {session['customer_id']}")
            print(f"   - created_at: {session['created_at']}")
            return session_id
        else:
            print(f"{RED}❌ Session not found{RESET}")
            return None
    except Exception as e:
        print(f"{RED}❌ Session management failed: {e}{RESET}")
        return None


def test_state_initialization():
    """Test SessionState initialization."""
    print(f"\n{YELLOW}[3/4] Testing SessionState Initialization...{RESET}")
    try:
        state: SessionState = {
            "session_id": "test_session",
            "customer_id": "test_customer",
            "started_at": datetime.now(),
            "user_input": "What is my loan status?",
            "language": "en",
            "confirmed_facts": {},
            "dynamic_context": [],
            "session_summaries": [],
            "extracted_entities": {},
            "detected_intent": "query_loan",
            "intent_confidence": 0.8,
            "has_mismatch": False,
            "mismatched_fields": {},
            "clarification_needed": False,
            "clarification_question": None,
            "user_confirmed_update": None,
            "memory_updates": [],
            "fields_changed": [],
            "query_type": None,
            "query_response": None,
            "agent_response": "",
            "model_temperature": 0.7,
            "max_tokens": 256,
            "total_tokens": 150,
            "should_summarize": False,
            "compression_ratio": 0.0,
            "summary": None,
            "error": None,
            "next_handler": "handle_query",
        }
        
        print(f"{GREEN}✅ SessionState initialized{RESET}")
        print(f"   - session_id: {state['session_id']}")
        print(f"   - customer_id: {state['customer_id']}")
        print(f"   - user_input: {state['user_input']}")
        print(f"   - detected_intent: {state['detected_intent']}")
        return state
    except Exception as e:
        print(f"{RED}❌ State initialization failed: {e}{RESET}")
        return None


def test_graph_invocation(state: SessionState):
    """Test graph.invoke() with sample state."""
    print(f"\n{YELLOW}[4/4] Testing Graph Invocation...{RESET}")
    try:
        print(f"   Starting orchestration...")
        graph = build_graph()
        
        print(f"   Invoking graph with state (async)...")
        result = asyncio.run(graph.ainvoke(state))
        
        print(f"{GREEN}✅ Graph invocation successful{RESET}")
        print(f"   - error: {result.get('error')}")
        print(f"   - detected_intent: {result.get('detected_intent')}")
        print(f"   - agent_response: {result.get('agent_response')[:100] if result.get('agent_response') else 'None'}...")
        print(f"   - next_handler: {result.get('next_handler')}")
        
        return result
    except Exception as e:
        print(f"{RED}❌ Graph invocation failed: {e}{RESET}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Run all tests."""
    print(f"\n{'='*70}")
    print(f"🧪 Agent Chat Integration Tests")
    print(f"{'='*70}")
    
    # Test 1: Graph compilation
    if not test_graph_compilation():
        print(f"\n{RED}Tests failed at graph compilation{RESET}")
        return False
    
    # Test 2: Session management
    session_id = test_session_management()
    if not session_id:
        print(f"\n{RED}Tests failed at session management{RESET}")
        return False
    
    # Test 3: State initialization
    state = test_state_initialization()
    if not state:
        print(f"\n{RED}Tests failed at state initialization{RESET}")
        return False
    
    # Test 4: Graph invocation
    result = test_graph_invocation(state)
    if not result:
        print(f"\n{RED}Tests failed at graph invocation{RESET}")
        return False
    
    print(f"\n{'='*70}")
    print(f"{GREEN}✅ All tests passed!{RESET}")
    print(f"{'='*70}\n")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
