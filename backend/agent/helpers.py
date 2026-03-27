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

from agent.schemas import FieldClassification, FieldClassificationResult
from agent.prompts import FIELD_CLASSIFICATION_PROMPT
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
