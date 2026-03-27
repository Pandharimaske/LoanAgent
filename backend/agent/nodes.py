"""
LangGraph Node Implementations for LoanAgent.

Each node is an async function that reads from and writes to SessionState.
Nodes are chained together in the LangGraph workflow.
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
    VECTOR_SEARCH_TOP_K,
)

logger = logging.getLogger(__name__)


# ============================================================================
# NODE 1: LOAD_MEMORY
# ============================================================================

async def load_memory(state: SessionState) -> SessionState:
    """
    Load customer memory from both SQLite and ChromaDB.
    
    - Tier 1: Confirmed structured facts from SQLite
    - Tier 2/3: Dynamic context + session summaries from ChromaDB
    
    Returns:
        Updated state with confirmed_facts, dynamic_context, session_summaries
    """
    try:
        customer_id = state.get("customer_id")
        if not customer_id:
            state["error"] = "No customer_id in state"
            return state
        
        # Load from SQLite (Tier 1)
        db = MemoryDatabase(db_path=SQLITE_PATH)
        db.connect()
        memory = db.load_memory(customer_id)
        db.close()
        
        confirmed_facts = {}
        if memory:
            # Extract confirmed facts from memory object
            if memory.monthly_income and memory.monthly_income.current:
                if memory.monthly_income.current.status == MemoryStatus.CONFIRMED:
                    confirmed_facts["monthly_income"] = memory.monthly_income.current.value
            
            if memory.cibil_score and memory.cibil_score.current:
                if memory.cibil_score.current.status == MemoryStatus.CONFIRMED:
                    confirmed_facts["cibil_score"] = memory.cibil_score.current.value
            
            if memory.employment_type and memory.employment_type.current:
                if memory.employment_type.current.status == MemoryStatus.CONFIRMED:
                    confirmed_facts["employment_type"] = memory.employment_type.current.value
        
        state["confirmed_facts"] = confirmed_facts
        logger.info(f"✅ Loaded {len(confirmed_facts)} confirmed facts for {customer_id}")
        
        # Load from ChromaDB (Tier 2/3)
        vs = VectorStore(persist_path=CHROMA_PATH)
        
        # Query for semantic matches
        user_input = state.get("user_input", "")
        if user_input:
            try:
                search_results = vs.search(customer_id, user_input, top_k=VECTOR_SEARCH_TOP_K)
                dynamic_context = [doc.get("text", "") for doc in search_results if doc.get("text")]
                state["dynamic_context"] = dynamic_context
                logger.info(f"✅ Retrieved {len(dynamic_context)} context chunks from ChromaDB")
            except Exception as e:
                logger.warning(f"ChromaDB search failed: {e}")
                state["dynamic_context"] = []
        else:
            state["dynamic_context"] = []
        
        # Session summaries (chronological)
        state["session_summaries"] = []  # TODO: Fetch from ChromaDB metadata filter
        
        return state
        
    except Exception as e:
        state["error"] = f"load_memory failed: {str(e)}"
        logger.error(state["error"])
        return state


# ============================================================================
# NODE 2: EXTRACT_ENTITIES
# ============================================================================

async def extract_entities(state: SessionState) -> SessionState:
    """
    Use Ollama to extract structured entities from user input.
    
    Returns a dict like:
    {
        "monthly_income": "₹45,000",
        "employment_type": "salaried",
        "co_applicant_name": "Anjali Kumar",
        ...
    }
    """
    try:
        user_input = state.get("user_input", "")
        language = state.get("language", "en")
        
        if not user_input:
            state["extracted_entities"] = {}
            return state
        
        # Build extraction prompt
        extraction_prompt = f"""You are a loan officer parsing customer input. Extract structured data.

Input language: {language}
User said: "{user_input}"

Extract these fields (if mentioned, otherwise omit):
- monthly_income
- employment_type
- property_location
- co_applicant_name
- existing_emi
- loan_amount_requested
- cibil_score

Response as JSON only (no markdown). Example:
{{"monthly_income": "₹50,000", "employment_type": "salaried"}}
"""
        
        client = OllamaClient()
        response = await client.generate(OLLAMA_MODEL, extraction_prompt)
        await client.close()
        
        # Parse JSON response
        try:
            extracted = json.loads(response.strip())
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse extraction response: {response}")
            extracted = {}
        
        state["extracted_entities"] = extracted
        logger.info(f"✅ Extracted {len(extracted)} entities")
        return state
        
    except Exception as e:
        state["error"] = f"extract_entities failed: {str(e)}"
        logger.error(state["error"])
        state["extracted_entities"] = {}
        return state


# ============================================================================
# NODE 3: DETECT_CONFLICTS
# ============================================================================

async def detect_conflicts(state: SessionState) -> SessionState:
    """
    Compare extracted entities against confirmed facts.
    Flag conflicts where new value differs from confirmed value.
    
    Returns list of conflicts:
    [
        {
            "field": "monthly_income",
            "existing_value": "₹45,000",
            "new_value": "₹50,000",
            "confidence": 0.95
        },
        ...
    ]
    """
    try:
        confirmed_facts = state.get("confirmed_facts", {})
        extracted_entities = state.get("extracted_entities", {})
        
        conflicts = []
        
        # Compare each extracted entity with confirmed fact
        for field, new_value in extracted_entities.items():
            if field in confirmed_facts:
                existing_value = confirmed_facts[field]
                if str(new_value).strip() != str(existing_value).strip():
                    conflicts.append({
                        "field": field,
                        "existing_value": existing_value,
                        "new_value": new_value,
                        "confidence": 0.90,  # TODO: Compute confidence from extraction model
                    })
        
        state["detected_conflicts"] = conflicts
        state["conflict_detected"] = len(conflicts) > 0
        
        if conflicts:
            logger.warning(f"⚠️  Detected {len(conflicts)} conflicts")
        else:
            logger.info("✅ No conflicts detected")
        
        return state
        
    except Exception as e:
        state["error"] = f"detect_conflicts failed: {str(e)}"
        logger.error(state["error"])
        state["detected_conflicts"] = []
        state["conflict_detected"] = False
        return state


# ============================================================================
# NODE 4: ASK_USER (if conflicts)
# ============================================================================

async def ask_user(state: SessionState) -> SessionState:
    """
    Generate clarification question for detected conflicts.
    Only called if conflict_detected == True.
    
    In production, this would send a question back to the user via API,
    wait for response, then update state.
    For now, we'll generate the question and note that a response is needed.
    """
    try:
        conflicts = state.get("detected_conflicts", [])
        
        if not conflicts:
            state["user_clarified"] = True
            return state
        
        # Build clarification prompt
        conflict_summary = "\n".join([
            f"- {c['field']}: you said '{c['new_value']}' but our records say '{c['existing_value']}'"
            for c in conflicts
        ])
        
        clarification_prompt = f"""You are a helpful loan officer. The customer said something that conflicts with our records:

{conflict_summary}

Ask a polite, concise clarification question. Respond with ONLY the question (no "I notice" preamble).
"""
        
        client = OllamaClient()
        question = await client.generate(OLLAMA_MODEL, clarification_prompt)
        await client.close()
        
        state["clarification_question"] = question.strip()
        state["user_clarified"] = False  # Awaiting response
        
        logger.info(f"❓ Generated clarification: {question[:50]}...")
        return state
        
    except Exception as e:
        state["error"] = f"ask_user failed: {str(e)}"
        logger.error(state["error"])
        state["user_clarified"] = True  # Skip if error
        return state


# ============================================================================
# NODE 5: RETRIEVE_CONTEXT
# ============================================================================

async def retrieve_context(state: SessionState) -> SessionState:
    """
    Retrieve semantic context from vector store to inject into LLM prompt.
    Already called in load_memory, but can be enhanced for specific queries.
    """
    try:
        # Context already loaded in load_memory
        # Here we could do additional filtering or re-ranking
        
        confirmed_facts = state.get("confirmed_facts", {})
        dynamic_context = state.get("dynamic_context", [])
        
        logger.info(f"✅ Context ready: {len(confirmed_facts)} facts + {len(dynamic_context)} context chunks")
        return state
        
    except Exception as e:
        state["error"] = f"retrieve_context failed: {str(e)}"
        logger.error(state["error"])
        return state


# ============================================================================
# NODE 6: SLM_INFERENCE
# ============================================================================

async def slm_inference(state: SessionState) -> SessionState:
    """
    Use Ollama to generate conversational response with memory injection.
    Injects confirmed facts and dynamic context into system prompt.
    """
    try:
        user_input = state.get("user_input", "")
        confirmed_facts = state.get("confirmed_facts", {})
        dynamic_context = state.get("dynamic_context", [])
        language = state.get("language", "en")
        
        # Build system prompt with memory
        system_prompt = """You are a helpful bank loan officer. You remember previous conversations and use that memory to provide personalized, accurate responses.

Be concise, natural, and conversational. Ask clarifying questions if needed.
Respond in the same language as the user."""
        
        if confirmed_facts:
            facts_str = "\n".join([f"- {k}: {v}" for k, v in confirmed_facts.items()])
            system_prompt += f"\n\nYou know about this customer:\n{facts_str}"
        
        if dynamic_context:
            context_str = "\n".join(dynamic_context[:3])  # Top 3
            system_prompt += f"\n\nRecent context:\n{context_str}"
        
        # Build full prompt
        full_prompt = f"{system_prompt}\n\nCustomer: {user_input}\n\nYou:"
        
        client = OllamaClient()
        response = await client.generate(
            OLLAMA_MODEL,
            full_prompt,
            temperature=state.get("model_temperature", 0.7),
            num_predict=state.get("max_tokens", 256),
        )
        await client.close()
        
        state["agent_response"] = response.strip()
        logger.info(f"✅ Generated response ({len(response.split())} words)")
        return state
        
    except Exception as e:
        state["error"] = f"slm_inference failed: {str(e)}"
        logger.error(state["error"])
        state["agent_response"] = "I encountered an error. Please try again."
        return state


# ============================================================================
# NODE 7: CHECK_TOKEN_THRESHOLD
# ============================================================================

async def check_token_threshold(state: SessionState) -> SessionState:
    """
    Check if conversation tokens exceed threshold.
    If so, set should_summarize=True for compression.
    """
    try:
        conversation_text = state.get("user_input", "") + state.get("agent_response", "")
        
        counter = TokenCounter()
        tokens = counter.count_text(conversation_text)
        
        state["total_tokens"] = tokens
        
        threshold = int(tokens * TOKEN_THRESHOLD_PERCENT)
        target = int(tokens * TOKEN_TARGET_PERCENT)
        
        if tokens > threshold:
            state["should_summarize"] = True
            state["compression_ratio"] = target / tokens if tokens > 0 else 0
            logger.info(f"⚠️  Token threshold exceeded: {tokens} > {threshold}")
        else:
            state["should_summarize"] = False
            logger.info(f"✅ Tokens OK: {tokens} < {threshold}")
        
        return state
        
    except Exception as e:
        state["error"] = f"check_token_threshold failed: {str(e)}"
        logger.error(state["error"])
        state["should_summarize"] = False
        return state


# ============================================================================
# NODE 8: END_SESSION
# ============================================================================

async def end_session(state: SessionState) -> SessionState:
    """
    Persist memory updates to SQLite and ChromaDB.
    Summarize conversation if needed.
    """
    try:
        customer_id = state.get("customer_id")
        session_id = state.get("session_id")
        extracted_entities = state.get("extracted_entities", {})
        user_input = state.get("user_input", "")
        agent_response = state.get("agent_response", "")
        
        if not customer_id:
            state["error"] = "No customer_id to persist"
            return state
        
        # Persist to SQLite
        db = MemoryDatabase(db_path=SQLITE_PATH)
        db.connect()
        
        # Load existing memory
        memory = db.load_memory(customer_id)
        if memory is None:
            from memory.models import CustomerMemoryNonPII
            memory = CustomerMemoryNonPII(customer_id=customer_id)
        
        # Update with extracted entities (mark as PENDING for user confirmation)
        for field, value in extracted_entities.items():
            if field == "monthly_income" and not memory.monthly_income or memory.monthly_income.current.status != "confirmed":
                from memory.models import FixedEntity, EntityRecord
                memory.monthly_income = FixedEntity(
                    current=EntityRecord(value=value, status=MemoryStatus.PENDING)
                )
        
        # Save
        db.save_memory(customer_id, memory)
        db.close()
        
        # Log to ChromaDB
        vs = VectorStore(persist_path=CHROMA_PATH)
        conversation_text = f"Customer: {user_input}\n\nAgent: {agent_response}"
        
        vs.add_document(
            customer_id=customer_id,
            text=conversation_text,
            session_id=session_id,
            doc_type="conversation",
            metadata={
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id,
            }
        )
        
        logger.info(f"✅ Persisted memory for {customer_id}")
        return state
        
    except Exception as e:
        state["error"] = f"end_session failed: {str(e)}"
        logger.error(state["error"])
        return state
