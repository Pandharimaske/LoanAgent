"""
LangGraph Node Implementations — Restructured Flow

Flow Order:
1. check_token_threshold - Check & summarize if needed (FIRST)
2. load_memory - Retrieve SQLite + ChromaDB context
3. extract_entities - Parse input, detect intent & mismatches
4. router - Decide which handler to use
5. Handlers: handle_memory_update / handle_query / handle_general
6. end_session - Persist all updates
"""

import sys
import logging
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.state import SessionState
from memory.sqlite_store import MemoryDatabase
from memory.vector_store import VectorStore
from memory.models import MemoryStatus
from utils.ollama_client import OllamaClient
from utils.tokenizer import TokenCounter, ContextWindow
from config import (
    SQLITE_PATH,
    CHROMA_PATH,
    OLLAMA_MODEL,
    TOKEN_THRESHOLD_PERCENT,
    TOKEN_TARGET_PERCENT,
    SESSION_CONTEXT_WINDOW,
    VECTOR_SEARCH_TOP_K,
)

logger = logging.getLogger(__name__)


# ============================================================================
# NODE 1: CHECK_TOKEN_THRESHOLD (FIRST - Session Start)
# ============================================================================

async def check_token_threshold(state: SessionState) -> SessionState:
    """
    Check if conversation exceeded token threshold.
    If yes, summarize and reset BEFORE processing new input.
    
    Runs FIRST in session lifecycle.
    """
    try:
        session_id = state.get("session_id", "unknown")
        current_tokens = state.get("total_tokens", 0)
        context_window = SESSION_CONTEXT_WINDOW
        threshold = int(context_window * TOKEN_THRESHOLD_PERCENT)
        
        logger.info(f"📊 Token Check: {current_tokens}/{threshold}")
        
        if current_tokens >= threshold:
            logger.warning(f"⚠️  Threshold exceeded - summarizing")
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
    
    Tier 1: Confirmed facts (income, CIBIL, etc)
    Tier 2/3: Dynamic context + summaries
    """
    try:
        customer_id = state.get("customer_id")
        if not customer_id:
            state["error"] = "No customer_id"
            return state
        
        # Load from SQLite
        db = MemoryDatabase(db_path=SQLITE_PATH)
        db.connect()
        memory = db.load_memory(customer_id)
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
                results = vs.search(customer_id, user_input, top_k=VECTOR_SEARCH_TOP_K)
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
# NODE 3: EXTRACT_ENTITIES
# ============================================================================

async def extract_entities(state: SessionState) -> SessionState:
    """
    Extract structured data from user input using Ollama.
    Detect intent and check for mismatches with confirmed facts.
    """
    try:
        user_input = state.get("user_input", "")
        confirmed_facts = state.get("confirmed_facts", {})
        
        if not user_input:
            state["error"] = "No user_input"
            return state
        
        prompt = f"""Extract data and detect intent.

USER: {user_input}
CONFIRMED: {json.dumps(confirmed_facts)}

Return JSON:
{{
    "extracted_entities": {{}},
    "detected_intent": "update_info|query_loan|ask_status|general",
    "intent_confidence": 0.0-1.0,
    "has_mismatch": boolean,
    "mismatched_fields": {{}}
}}"""
        
        client = OllamaClient()
        response = await client.generate_async(prompt, model=OLLAMA_MODEL)
        
        try:
            result = json.loads(response)
            state["extracted_entities"] = result.get("extracted_entities", {})
            state["detected_intent"] = result.get("detected_intent", "general_chat")
            state["intent_confidence"] = result.get("intent_confidence", 0.5)
            state["has_mismatch"] = result.get("has_mismatch", False)
            state["mismatched_fields"] = result.get("mismatched_fields", {})
            logger.info(f"🎯 Intent: {state['detected_intent']}")
        except json.JSONDecodeError as je:
            logger.error(f"JSON parse error: {je}")
            state["detected_intent"] = "general_chat"
            state["has_mismatch"] = False
            state["extracted_entities"] = {}
            state["mismatched_fields"] = {}
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Extraction failed: {e}")
        state["error"] = str(e)
        return state


# ============================================================================
# NODE 4: ROUTER
# ============================================================================

async def router(state: SessionState) -> SessionState:
    """
    Route to appropriate handler based on intent and mismatch detection.
    
    Logic:
    - If has_mismatch → handle_memory_update
    - Else if intent is query → handle_query
    - Else → handle_general
    """
    try:
        has_mismatch = state.get("has_mismatch", False)
        intent = state.get("detected_intent", "general_chat")
        
        if has_mismatch:
            state["next_handler"] = "handle_memory_update"
            logger.info("→ handle_memory_update (mismatch)")
        elif intent in ["query_loan", "ask_status"]:
            state["next_handler"] = "handle_query"
            logger.info(f"→ handle_query ({intent})")
        else:
            state["next_handler"] = "handle_general"
            logger.info("→ handle_general")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Router failed: {e}")
        state["next_handler"] = "handle_general"
        return state


# ============================================================================
# NODE 5a: HANDLE_MEMORY_UPDATE
# ============================================================================

async def handle_memory_update(state: SessionState) -> SessionState:
    """
    Handle when user provided new/conflicting information.
    Ask for clarification on mismatched fields.
    """
    try:
        mismatched = state.get("mismatched_fields", {})
        
        if not mismatched:
            state["agent_response"] = "Thank you for the information."
            return state
        
        fields = list(mismatched.keys())
        state["clarification_question"] = f"Could you please confirm: {', '.join(fields)}?"
        state["clarification_needed"] = True
        
        logger.info(f"❓ Asking for clarification")
        state["agent_response"] = state["clarification_question"]
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Update handler failed: {e}")
        state["agent_response"] = "I encountered an error"
        return state


# ============================================================================
# NODE 5b: HANDLE_QUERY
# ============================================================================

async def handle_query(state: SessionState) -> SessionState:
    """
    Answer questions using confirmed facts and context.
    """
    try:
        user_input = state.get("user_input", "")
        facts = state.get("confirmed_facts", {})
        context = state.get("dynamic_context", [])[:2]
        
        prompt = f"""Answer the question using facts and context.

FACTS: {json.dumps(facts)}
CONTEXT: {context}

QUESTION: {user_input}

Answer:"""
        
        client = OllamaClient()
        response = await client.generate_async(prompt, model=OLLAMA_MODEL)
        
        state["query_response"] = response
        state["agent_response"] = response
        logger.info("💬 Query answered")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Query handler failed: {e}")
        state["agent_response"] = "Unable to answer"
        return state


# ============================================================================
# NODE 5c: HANDLE_GENERAL
# ============================================================================

async def handle_general(state: SessionState) -> SessionState:
    """
    General conversation with memory injection.
    """
    try:
        user_input = state.get("user_input", "")
        facts = state.get("confirmed_facts", {})
        context = state.get("dynamic_context", [])[:2]
        
        prompt = f"""You are a helpful loan officer.

CUSTOMER: {json.dumps(facts)}
CONTEXT: {context}

USER: {user_input}

Response:"""
        
        client = OllamaClient()
        response = await client.generate_async(prompt, model=OLLAMA_MODEL)
        
        state["agent_response"] = response
        logger.info("💬 Response sent")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Handler failed: {e}")
        state["agent_response"] = "I encountered an error"
        return state


# ============================================================================
# NODE 6: END_SESSION
# ============================================================================

async def end_session(state: SessionState) -> SessionState:
    """
    Persist all updates to SQLite and ChromaDB.
    """
    try:
        customer_id = state.get("customer_id")
        session_id = state.get("session_id")
        agent_response = state.get("agent_response", "")
        
        if not customer_id:
            state["error"] = "No customer_id"
            return state
        
        logger.info(f"💾 Persisting session {session_id}...")
        
        # Store to ChromaDB
        vs = VectorStore(persist_path=CHROMA_PATH)
        vs.add(
            customer_id=customer_id,
            documents=[agent_response[:500]],
            metadatas=[{
                "session_id": session_id,
                "timestamp": datetime.now().isoformat()
            }],
        )
        
        logger.info(f"✅ Session persisted")
        state["session_end_time"] = datetime.now().isoformat()
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Persistence failed: {e}")
        state["error"] = str(e)
        return state
