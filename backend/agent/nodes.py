"""
LangGraph Node Implementations — Restructured Flow

Flow Order:
1. check_token_threshold - Check & summarize if needed (FIRST)
2. load_memory - Retrieve SQLite + ChromaDB context
3. router - LLM-based intelligent routing using Pydantic structured output
4. Handlers:
   - handle_mismatch_confirmation - Ask user to verify conflicting data (with historical context)
   - handle_memory_update - Acknowledge new/additional information
   - handle_query - Answer questions about loan/status
   - handle_general - General conversation
5. end_session - Persist all updates
"""

import sys
import logging
import json
from pathlib import Path
from typing import Dict, Any, Literal
from datetime import datetime
from pydantic import BaseModel, Field
from langchain_community.chat_models import ChatOllama

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.state import SessionState
from agent.prompts import (
    ROUTER_PROMPT,
    MEMORY_UPDATE_ACKNOWLEDGMENT,
    QUERY_ANSWER_CHAT_PROMPT,
    GENERAL_RESPONSE_PROMPT,
    MISMATCH_VERIFICATION_PROMPT,
    CONFLICT_EXTRACTION_PROMPT,
)
from memory.sqlite_store import MemoryDatabase
from memory.vector_store import VectorStore
from memory.models import MemoryStatus
from config import (
    SQLITE_PATH,
    CHROMA_PATH,
    OLLAMA_MODEL,
    OLLAMA_BASE_URL,
    TOKEN_THRESHOLD_PERCENT,
    SESSION_CONTEXT_WINDOW,
    VECTOR_SEARCH_TOP_K,
)

logger = logging.getLogger(__name__)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class ConflictDetail(BaseModel):
    """Details of a single conflicting field."""
    field: str = Field(..., description="Field name that has conflict")
    old_value: Any = Field(..., description="Previously confirmed value")
    new_value: Any = Field(..., description="New value from customer")
    confidence: float = Field(..., description="Confidence of conflict detection (0.0-1.0)")
    explanation: str = Field(..., description="Why this conflict matters")


class ConflictExtractionResult(BaseModel):
    """LLM analysis result for conflict extraction."""
    has_conflicts: bool = Field(..., description="Whether any conflicts were found")
    conflicts: list[ConflictDetail] = Field(default_factory=list, description="List of conflicts detected")
    summary: str = Field(..., description="Summary of analysis")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def extract_conflicts_with_llm(
    user_input: str,
    confirmed_facts: Dict[str, Any],
    dynamic_context: list,
) -> Dict[str, Dict[str, Any]]:
    """
    Use LLM to detect and extract conflicts from user input.
    
    Args:
        user_input: Customer's current message
        confirmed_facts: Previously verified facts from SQLite
        dynamic_context: Historical context from ChromaDB
    
    Returns:
        {field: {old_value, new_value, confidence, explanation}} for conflicting fields
    """
    try:
        if not confirmed_facts or not user_input:
            return {}
        
        # Prepare context
        facts_summary = json.dumps(confirmed_facts, indent=2)
        context_summary = "\n".join(dynamic_context[:3]) if dynamic_context else "No context available"
        
        # Create LLM chain for conflict extraction
        llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.2,  # Lower temp for precise analysis
        )
        
        structured_llm = llm.with_structured_output(ConflictExtractionResult)
        chain = CONFLICT_EXTRACTION_PROMPT | structured_llm
        
        # Extract conflicts
        result = await chain.ainvoke(
            {
                "user_input": user_input,
                "facts_summary": facts_summary,
                "context_summary": context_summary,
            }
        )
        
        # Convert to state format
        conflicts = {}
        for conflict in result.conflicts:
            conflicts[conflict.field] = {
                "old_value": conflict.old_value,
                "new_value": conflict.new_value,
                "confidence": conflict.confidence,
                "explanation": conflict.explanation,
            }
        
        logger.info(f"🔍 LLM Conflict Analysis: Found {len(conflicts)} conflict(s)")
        if conflicts:
            logger.debug(f"   Conflicts: {list(conflicts.keys())}")
            logger.debug(f"   Summary: {result.summary}")
        
        return conflicts
        
    except Exception as e:
        logger.error(f"❌ Conflict extraction failed: {e}")
        return {}


# ============================================================================
# PYDANTIC MODELS FOR STRUCTURED OUTPUT
# ============================================================================

class RouterDecision(BaseModel):
    """Structured routing decision from LLM analysis.
    
    The routing decision itself indicates the state:
    - If next_handler == "handle_mismatch_confirmation" → has mismatch (conflicts detected)
    - If next_handler == "handle_memory_update" → new info only (no conflicts)
    - If next_handler == "handle_query" → user asking questions
    - If next_handler == "handle_general" → general conversation
    """
    next_handler: Literal[
        "handle_mismatch_confirmation",
        "handle_memory_update",
        "handle_query",
        "handle_general"
    ] = Field(
        ...,
        description="Next handler to invoke based on detected intent/mismatch"
    )
    reasoning: str = Field(
        ...,
        description="Why this handler was chosen and what was detected"
    )
    confidence: float = Field(
        ...,
        description="Confidence score 0.0-1.0"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "next_handler": "handle_mismatch_confirmation",
                "reasoning": "User mentioned income change. Previous: 50000, Now: 75000. Routing to mismatch handler for polite verification.",
                "confidence": 0.92
            }
        }


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
        
        # ====================================================================
        # CONFIGURE LLM WITH STRUCTURED OUTPUT
        # ====================================================================
        # Initialize base LLM
        base_llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.3,
        )
        
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
# NODE 5a: HANDLE_MEMORY_UPDATE
# ============================================================================

async def handle_memory_update(state: SessionState) -> SessionState:
    """
    Handle when user provided NEW information (no conflicts).
    
    This handler is for:
    - Completely new facts (not previously recorded)
    - Additional details that don't conflict with confirmed data
    
    For CONFLICTING information, see: handle_mismatch_confirmation
    """
    try:
        user_input = state.get("user_input", "")
        
        logger.info("📝 Memory Update Handler (New Info):")
        logger.info(f"   User Input: {user_input[:100]}...")
        
        # Acknowledge new information
        state["agent_response"] = MEMORY_UPDATE_ACKNOWLEDGMENT
        logger.info("✅ New information acknowledged and stored")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Memory update handler failed: {e}")
        state["agent_response"] = "I encountered an error storing this information. Please try again."
        return state


# ============================================================================
# NODE 5a(b): HANDLE_MISMATCH_CONFIRMATION (New Dedicated Node)
# ============================================================================

async def handle_mismatch_confirmation(state: SessionState) -> SessionState:
    """
    Handle when user provided CONFLICTING information.
    
    Politely asks the user to verify/confirm the new value while mentioning
    WHEN the previous information was recorded.
    
    Router has already identified:
    1. has_mismatch: True (there are conflicts)
    2. mismatched_fields: {field: {old_value, new_value, ...}}
    3. dynamic_context: Historical info from ChromaDB (may contain timestamps)
    """
    try:
        mismatches = state.get("mismatched_fields", {})
        dynamic_context = state.get("dynamic_context", [])
        confirmed_facts = state.get("confirmed_facts", {})
        
        logger.info("🔍 Mismatch Confirmation Handler:")
        logger.info(f"   Conflicts Found: {len(mismatches)}")
        logger.info(f"   Fields: {list(mismatches.keys())}")
        
        if not mismatches:
            # Fallback if no mismatches despite being routed here
            state["agent_response"] = MEMORY_UPDATE_ACKNOWLEDGMENT
            logger.warning("⚠️  No mismatches found despite routing to mismatch handler")
            return state
        
        # ====================================================================
        # BUILD MISMATCH DETAILS WITH EXPLANATIONS FROM LLM
        # ====================================================================
        mismatch_details_parts = []
        for field, conflict_info in mismatches.items():
            old_val = conflict_info.get("old_value", "unknown")
            new_val = conflict_info.get("new_value", "unknown")
            confidence = conflict_info.get("confidence", 0.0)
            explanation = conflict_info.get("explanation", "Data changed")
            
            detail = f"• {field.replace('_', ' ').title()}\n"
            detail += f"  Previous: {old_val}\n"
            detail += f"  Current: {new_val}\n"
            detail += f"  Status: {explanation}\n"
            detail += f"  Confidence: {confidence:.0%}"
            
            mismatch_details_parts.append(detail)
        
        mismatch_details = "\n\n".join(mismatch_details_parts)
        
        # ====================================================================
        # BUILD HISTORICAL CONTEXT (hint at when old data was recorded)
        # ====================================================================
        # Try to extract timeline info from ChromaDB results
        historical_context = "Unknown date"
        
        if dynamic_context:
            # Look for date/time references in context
            context_text = " ".join(dynamic_context[:3])
            
            # Simple date extraction (you can enhance this with better parsing)
            if "Monday" in context_text or "Tuesday" in context_text or \
               "Wednesday" in context_text or "Thursday" in context_text or \
               "Friday" in context_text or "Saturday" in context_text or \
               "Sunday" in context_text or "ago" in context_text:
                historical_context = context_text[:200]  # Use first 200 chars
            else:
                # Fallback: mention it was previously recorded
                historical_context = "a previous session"
        
        # ====================================================================
        # PREPARE CONTEXT FOR LLM CHAIN
        # ====================================================================
        customer_profile = json.dumps(confirmed_facts, indent=2) if confirmed_facts else "{}"
        
        # ====================================================================
        # INVOKE MISMATCH VERIFICATION PROMPT WITH LLM
        # ====================================================================
        llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.5,  # Balanced - professional but warm
        )
        
        chain = MISMATCH_VERIFICATION_PROMPT | llm
        
        response = await chain.ainvoke(
            {
                "mismatch_details": mismatch_details,
                "historical_context": historical_context,
                "customer_profile": customer_profile,
            }
        )
        
        confirmation_message = response.content if hasattr(response, 'content') else str(response)
        
        state["clarification_question"] = confirmation_message
        state["clarification_needed"] = True
        state["agent_response"] = confirmation_message
        
        logger.info("❓ Polite mismatch confirmation request generated")
        logger.info(f"   Asking customer to confirm {len(mismatches)} field(s)")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Mismatch confirmation handler failed: {e}")
        state["agent_response"] = (
            "I noticed some differences in your information and I'd like to verify them with you. "
            "Could you please confirm the current details? "
        )
        return state


# ============================================================================
# NODE 5b: HANDLE_QUERY
# ============================================================================

async def handle_query(state: SessionState) -> SessionState:
    """
    Answer questions using confirmed facts and context.
    
    Uses ChatOllama with structured prompts from prompts.py for consistency
    and maintainability.
    """
    try:
        user_input = state.get("user_input", "")
        facts = state.get("confirmed_facts", {})
        context = state.get("dynamic_context", [])[:2]
        
        # Prepare context summaries
        facts_summary = json.dumps(facts, indent=2) if facts else "No confirmed facts"
        context_summary = "\n".join(context) if context else "No available context"
        
        # Create LLM chain
        llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.3,
        )
        
        # Use the query prompt from prompts.py
        chain = QUERY_ANSWER_CHAT_PROMPT | llm
        
        response = await chain.ainvoke(
            {
                "user_input": user_input,
                "facts_summary": facts_summary,
                "context_summary": context_summary,
            }
        )
        
        answer = response.content if hasattr(response, 'content') else str(response)
        
        state["query_response"] = answer
        state["agent_response"] = answer
        logger.info("💬 Query answered")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ Query handler failed: {e}")
        state["agent_response"] = "I apologize, I'm unable to answer that question at the moment. Please try again."
        return state


# ============================================================================
# NODE 5c: HANDLE_GENERAL
# ============================================================================

async def handle_general(state: SessionState) -> SessionState:
    """
    General conversation with memory injection.
    
    Uses ChatOllama with structured prompts from prompts.py.
    Injects customer context to personalize responses.
    """
    try:
        user_input = state.get("user_input", "")
        facts = state.get("confirmed_facts", {})
        context = state.get("dynamic_context", [])[:2]
        
        # Prepare context summaries
        facts_summary = json.dumps(facts, indent=2) if facts else "No customer profile yet"
        context_summary = "\n".join(context) if context else "No previous context"
        
        # Create LLM chain
        llm = ChatOllama(
            model=OLLAMA_MODEL,
            base_url=OLLAMA_BASE_URL,
            temperature=0.7,  # Slightly higher for conversational tone
        )
        
        # Use the general response prompt from prompts.py
        chain = GENERAL_RESPONSE_PROMPT | llm
        
        response = await chain.ainvoke(
            {
                "user_input": user_input,
                "facts_summary": facts_summary,
                "context_summary": context_summary,
            }
        )
        
        answer = response.content if hasattr(response, 'content') else str(response)
        
        state["agent_response"] = answer
        logger.info("💬 Response sent")
        
        return state
        
    except Exception as e:
        logger.error(f"❌ General handler failed: {e}")
        state["agent_response"] = "I encountered an error while processing your request. Please try again."
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
