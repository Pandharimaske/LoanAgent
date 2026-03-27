"""
Core infrastructure nodes for LangGraph workflow.

Nodes:
- check_token_threshold: Monitor and summarize if tokens exceed threshold
- load_memory: Retrieve customer context from SQLite + ChromaDB
- router: LLM-based intelligent routing to appropriate handler
- end_session: Persist all updates after session completes
"""

import sys
import logging
import json
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.state import SessionState
from agent.prompts import ROUTER_PROMPT
from agent.schemas import RouterDecision
from agent.helpers import extract_conflicts_with_llm, format_conversation_history, create_llm
from memory.sqlite_store import MemoryDatabase
from memory.vector_store import VectorStore
from memory.models import MemoryStatus
from config import (
    SQLITE_PATH,
    CHROMA_PATH,
    TOKEN_THRESHOLD_PERCENT,
    SESSION_CONTEXT_WINDOW,
    VECTOR_SEARCH_TOP_K,
)

logger = logging.getLogger(__name__)


# ============================================================================
# NODE 1: CHECK_TOKEN_THRESHOLD
# ============================================================================

async def check_token_threshold(state: SessionState) -> SessionState:
    """
    Check if conversation exceeded token threshold.
    If yes, summarize and reset BEFORE processing new input.
    
    Runs FIRST in session lifecycle.
    """
    try:
        current_tokens = state.get("total_tokens", 0)
        context_window = SESSION_CONTEXT_WINDOW
        threshold = int(context_window * TOKEN_THRESHOLD_PERCENT)
        
        logger.info(f"📊 Token Check: {current_tokens}/{threshold}")
        
        if current_tokens >= threshold:
            logger.warning("⚠️  Threshold exceeded - summarizing")
            state["should_summarize"] = True
            state["summary"] = "[Summary pending - compress conversation]"
            state["total_tokens"] = 0
        else:
            state["should_summarize"] = False
            state["summary"] = None
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Token check failed: {e}")
        state["error"] = str(e)
        return state


# ============================================================================
# NODE 2: LOAD_MEMORY
# ============================================================================

async def load_memory(state: SessionState) -> SessionState:
    """
    Load customer memory from SQLite (Tier 1) + ChromaDB (Tier 2/3).
    
    Also initializes conversation message history if not already done.
    
    Tier 1: Confirmed facts (income, CIBIL, etc)
    Tier 2/3: Dynamic context + summaries
    """
    try:
        customer_id = state.get("customer_id")
        if not customer_id:
            state["error"] = "No customer_id"
            return state
        
        # ====================================================================
        # INITIALIZE MESSAGE HISTORY
        # ====================================================================
        if "messages" not in state or not state.get("messages"):
            state["messages"] = []
        
        # Add current user input to message history
        user_input = state.get("user_input", "")
        if user_input:
            state["messages"].append({
                "role": "user",
                "content": user_input,
                "timestamp": datetime.now().isoformat()
            })
            logger.info(f"📝 Message added to history (total: {len(state['messages'])})")
        
        # Load from SQLite
        db = MemoryDatabase(db_path=SQLITE_PATH)
        db.connect()
        memory = db.load_customer_memory(customer_id)
        db.close()
        
        confirmed_facts = {}
        if memory:
            if hasattr(memory, 'monthly_income') and memory.monthly_income:
                if hasattr(memory.monthly_income, 'current') and memory.monthly_income.current:
                    if memory.monthly_income.current.status == MemoryStatus.CONFIRMED:
                        confirmed_facts["monthly_income"] = memory.monthly_income.current.value
            
            if hasattr(memory, 'cibil_score') and memory.cibil_score:
                if hasattr(memory.cibil_score, 'current') and memory.cibil_score.current:
                    if memory.cibil_score.current.status == MemoryStatus.CONFIRMED:
                        confirmed_facts["cibil_score"] = memory.cibil_score.current.value
        
        state["confirmed_facts"] = confirmed_facts
        logger.info(f"✅ Loaded {len(confirmed_facts)} confirmed facts")
        
        # Load from ChromaDB
        vs = VectorStore(persist_path=CHROMA_PATH)
        user_input = state.get("user_input", "")
        
        if user_input:
            try:
                results = vs.search(customer_id, user_input, n_results=VECTOR_SEARCH_TOP_K)
                dynamic_context = [doc.get("text", "") for doc in results if doc.get("text")]
                state["dynamic_context"] = dynamic_context
                logger.info(f"✅ Retrieved {len(dynamic_context)} chunks from ChromaDB")
            except Exception as e:
                logger.warning(f"⚠️  ChromaDB search failed: {e}")
                state["dynamic_context"] = []
        else:
            state["dynamic_context"] = []
        
        state["session_summaries"] = []
        return state
        
    except Exception as e:
        logger.error(f"❌ Memory load failed: {e}")
        state["error"] = str(e)
        return state


# ============================================================================
# NODE 3: ROUTER
# ============================================================================

async def router(state: SessionState) -> SessionState:
    """
    LLM-based Intelligent Router using LangChain's structured output binding.
    
    This router uses llm.with_structured_output(RouterDecision) to ensure
    the LLM response is automatically validated and parsed into a Pydantic model.
    
    INPUT:
    - user_input: Customer's current message
    - confirmed_facts: Verified customer information from SQLite
    - dynamic_context: Relevant historical context from ChromaDB
    
    OUTPUT:
    - next_handler: Which node processes this (handle_memory_update, handle_query, handle_general)
    - has_mismatch: Whether user input conflicts with confirmed data
    - detected_conflicts: Details of any conflicts found
    - reasoning & confidence: Explanation for audit/debugging
    """
    try:
        user_input = state.get("user_input", "")
        confirmed_facts = state.get("confirmed_facts", {})
        dynamic_context = state.get("dynamic_context", [])
        
        if not user_input:
            state["next_handler"] = "handle_general"
            state["error"] = "No user input provided"
            logger.warning("⚠️  Router: No user input")
            return state
        
        # ====================================================================
        # PREPARE CONTEXT FOR PROMPT
        # ====================================================================
        context_summary = "\n".join(dynamic_context[:3]) if dynamic_context else "No relevant context found"
        facts_summary = json.dumps(confirmed_facts, indent=2) if confirmed_facts else "No confirmed facts"
        
        # Format conversation history
        messages = state.get("messages", [])
        conversation_history = format_conversation_history(messages[:-1] if messages else [])  # Exclude current message
        
        # ====================================================================
        # CONFIGURE LLM WITH STRUCTURED OUTPUT
        # ====================================================================
        # Initialize base LLM with consistent configuration
        base_llm = create_llm(temperature=0.3)
        
        # Bind Pydantic schema to LLM - ensures responses are validated/parsed automatically
        # This is better than manual JSON parsing because:
        # 1. Validation happens at LLM level
        # 2. Retries happen automatically for invalid structures
        # 3. Type safety guaranteed when accessing fields
        structured_llm = base_llm.with_structured_output(RouterDecision)
        
        # ====================================================================
        # CREATE CHAIN: PROMPT → STRUCTURED LLM → PARSED OUTPUT
        # ====================================================================
        chain = ROUTER_PROMPT | structured_llm
        
        # ====================================================================
        # INVOKE CHAIN - returns RouterDecision (already parsed & validated)
        # ====================================================================
        decision = await chain.ainvoke(
            {
                "user_input": user_input,
                "facts_summary": facts_summary,
                "context_summary": context_summary,
                "conversation_history": conversation_history,
            }
        )
        
        # ====================================================================
        # STORE DECISION IN STATE & DETECT CONFLICTS (LLM-based)
        # ====================================================================
        state["next_handler"] = decision.next_handler
        state["router_reasoning"] = decision.reasoning
        state["router_confidence"] = decision.confidence
        
        # If routing to mismatch handler, use LLM to detect and analyze conflicts
        if decision.next_handler == "handle_mismatch_confirmation":
            logger.info("🔍 Analyzing conflicts with LLM...")
            mismatches = await extract_conflicts_with_llm(
                user_input, confirmed_facts, dynamic_context
            )
            state["mismatched_fields"] = mismatches
            state["has_mismatch"] = bool(mismatches)
        else:
            state["mismatched_fields"] = {}
            state["has_mismatch"] = False
        
        # ====================================================================
        # LOG ROUTING DECISION
        # ====================================================================
        logger.info("🤖 Router Decision:")
        logger.info(f"   Handler: {decision.next_handler}")
        logger.info(f"   Reasoning: {decision.reasoning}")
        logger.info(f"   Confidence: {decision.confidence:.2f}")
        if state["has_mismatch"]:
            logger.info(f"   Conflicts Detected: {len(state['mismatched_fields'])} field(s)")
        logger.info(f"→ Routing to: {decision.next_handler}")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Router failed: {e}")
        logger.debug(f"   Error details: {str(e)}")
        state["next_handler"] = "handle_general"
        state["error"] = f"Router error: {str(e)}"
        state["has_mismatch"] = False
        state["mismatched_fields"] = {}
        state["router_reasoning"] = "Fallback due to error"
        state["router_confidence"] = 0.3
        logger.info("→ Fallback to: handle_general")
        return state


# ============================================================================
# NODE 6: END_SESSION
# ============================================================================

async def end_session(state: SessionState) -> SessionState:
    """
    Persist all updates to SQLite and ChromaDB.
    Also adds agent response to message history for future context.
    """
    try:
        customer_id = state.get("customer_id")
        session_id = state.get("session_id")
        agent_response = state.get("agent_response", "")
        
        if not customer_id:
            state["error"] = "No customer_id"
            return state
        
        logger.info(f"💾 Persisting session {session_id}...")
        
        # Add agent response to message history
        if "messages" not in state:
            state["messages"] = []
        
        state["messages"].append({
            "role": "assistant",
            "content": agent_response,
            "timestamp": datetime.now().isoformat()
        })
        logger.info(f"📝 Agent response added to history (total: {len(state['messages'])})")
        
        # Store to ChromaDB
        vs = VectorStore(persist_path=CHROMA_PATH)
        vs.add_chunk(
            customer_id=customer_id,
            session_id=session_id,
            text=agent_response[:500],
            topic_tag="response",
        )
        
        logger.info("✅ Session persisted")
        state["session_end_time"] = datetime.now().isoformat()
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Persistence failed: {e}")
        state["error"] = str(e)
        return state
