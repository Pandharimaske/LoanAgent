"""
Helper functions for LLM-based analysis and classification.

Functions:
- create_llm: Factory function for consistent ChatOllama initialization
- format_conversation_history: Format message history for LLM context
- extract_conflicts_with_llm: Detect conflicts between user input and confirmed facts
- classify_fields_with_llm: Classify fields as schema or contextual information
"""

import sys
import logging
import json
from pathlib import Path
from typing import Dict, Any, List
from langchain_ollama import ChatOllama

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent.schemas import ConflictExtractionResult, FieldClassification, FieldClassificationResult
from agent.prompts import CONFLICT_EXTRACTION_PROMPT, FIELD_CLASSIFICATION_PROMPT
from config import OLLAMA_MODEL, OLLAMA_BASE_URL, OLLAMA_TIMEOUT

logger = logging.getLogger(__name__)


def create_llm(temperature: float = 0.3, timeout: int = None) -> ChatOllama:
    """
    Factory function to create consistently configured ChatOllama instances.
    
    Args:
        temperature: Temperature for response generation (0.0-1.0)
        timeout: Request timeout in seconds (default from config)
    
    Returns:
        Configured ChatOllama instance ready for use
    """
    if timeout is None:
        timeout = OLLAMA_TIMEOUT
    
    return ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=temperature,
        timeout=timeout,
        # NOTE: Do NOT set format="json" here.
        # with_structured_output() passes a full JSON Schema object as the
        # Ollama `format` param. Simultaneously setting format="json" (a plain
        # string) causes Ollama to reject the request with:
        #   "invalid JSON schema in format" (status 500)
    )


def format_conversation_history(messages: List[Dict[str, str]], max_turns: int = 5) -> str:
    """
    Format message history into readable context for LLM.
    
    Args:
        messages: List of message dicts with "role" and "content"
        max_turns: Maximum number of recent turns to include
    
    Returns:
        Formatted conversation history string
    """
    if not messages:
        return "No previous conversation"
    
    # Get last N turns (each turn = user + assistant)
    recent_messages = messages[-(max_turns * 2):]
    
    history_lines = []
    for msg in recent_messages:
        role = msg.get("role", "unknown").upper()
        content = msg.get("content", "")
        history_lines.append(f"{role}: {content}")
    
    return "\n".join(history_lines) if history_lines else "No previous conversation"


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
        llm = create_llm(temperature=0.2)  # Lower temp for precise analysis
        
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
        
        # Convert to state format using model_dump()
        conflicts = {}
        for conflict in result.conflicts:
            conflicts[conflict.field] = conflict.model_dump(exclude={"field"})
        
        logger.info(f"🔍 LLM Conflict Analysis: Found {len(conflicts)} conflict(s)")
        if conflicts:
            logger.debug(f"   Conflicts: {list(conflicts.keys())}")
            logger.debug(f"   Summary: {result.summary}")
        
        return conflicts
        
    except Exception as e:
        logger.error(f"❌ Conflict extraction failed: {e}")
        return {}


async def classify_fields_with_llm(
    user_input: str,
    memory_context: str = "No context available",
    conversation_history: str = "No prior conversation"
) -> Dict[str, FieldClassification]:
    """
    Use LLM to classify incoming information as schema fields or contextual info.
    
    Args:
        user_input: Customer's statement
        memory_context: Formatted memory block containing known facts and context
        conversation_history: Formatted string of the recent conversation
    
    Returns:
        {field_name: FieldClassification} for each classified field
    """
    try:
        llm = create_llm(temperature=0.2)
        
        structured_llm = llm.with_structured_output(FieldClassificationResult)
        chain = FIELD_CLASSIFICATION_PROMPT | structured_llm
        
        result = await chain.ainvoke({
            "user_input": user_input,
            "memory_context": memory_context,
            "conversation_history": conversation_history
        })
        
        # Return classifications as dict using model_dump()
        classifications = {
            clf.field_name: clf for clf in result.classifications
        }
        
        logger.info(f"🏷️  Field Classification: {len(classifications)} fields classified")
        logger.debug(f"   Summary: {result.summary}")
        
        return classifications
        
    except Exception as e:
        logger.error(f"❌ Field classification failed: {e}")
        return {}
