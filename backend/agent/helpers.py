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

from agent.schemas import ExtractionResult, ExtractedField
from agent.prompts import EXTRACTION_PROMPT, QUERY_REWRITE_PROMPT
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


async def rewrite_query_for_retrieval(
    user_input: str,
    conversation_history: str,
) -> str:
    """
    Context-aware query rewriting for ChromaDB retrieval.

    Instead of using the raw user message (which may contain pronouns,
    vague references, or conversational phrasing), ask the LLM to produce
    a compact, keyword-dense retrieval query.

    Examples:
        "what did I say about my job earlier?" →
            "employment, employer name, job title, work experience, income source"

        "Mine" (in context of income question) →
            "monthly income, salary, income amount"

    Falls back to the original user_input if the LLM call fails.
    """
    try:
        llm = create_llm(temperature=0.1)  # Very low temp — deterministic
        chain = QUERY_REWRITE_PROMPT | llm
        response = await chain.ainvoke({
            "user_input":           user_input,
            "conversation_history": conversation_history or "No prior conversation",
        })
        rewritten = (response.content if hasattr(response, "content") else str(response)).strip()
        # Sanity check — empty or too long → fall back
        if not rewritten or len(rewritten) > 200:
            return user_input
        logger.info(f"🔍 Query rewritten: '{user_input[:40]}' → '{rewritten[:60]}'")
        return rewritten
    except Exception as e:
        logger.warning(f"⚠️  Query rewrite failed (using original): {e}")
        return user_input


async def extract_fields_with_llm(
    user_input: str,
    memory_context: str = "No context available",
    conversation_history: str = "No prior conversation",
) -> List[ExtractedField]:
    """
    Extract all facts from the user's message using the LLM.

    Returns a flat list of ExtractedField objects.
    Each field has: key, value, is_correction.

    Routing (SQLite vs ChromaDB) is NOT done here — the caller decides
    by checking whether field.key is in CustomerMemory.model_fields.
    """
    try:
        llm = create_llm(temperature=0.1)  # Low temp for deterministic extraction
        structured_llm = llm.with_structured_output(ExtractionResult)
        chain = EXTRACTION_PROMPT | structured_llm

        result: ExtractionResult = await chain.ainvoke({
            "user_input":          user_input,
            "memory_context":      memory_context,
            "conversation_history": conversation_history,
        })

        fields = result.fields or []
        logger.info(f"📊 Extraction: {len(fields)} field(s) | {result.summary}")
        for f in fields:
            logger.debug(f"   {'[CORRECTION]' if f.is_correction else ''} {f.key}={f.value!r}")
        return fields

    except Exception as e:
        logger.error(f"❌ extract_fields_with_llm failed: {e}")
        return []


# Keep backward-compat alias used by any leftover imports
async def classify_fields_with_llm(
    user_input: str,
    memory_context: str = "No context available",
    conversation_history: str = "No prior conversation",
    **_,
) -> dict:
    """Deprecated: use extract_fields_with_llm instead."""
    from agent.schemas import FieldClassification
    fields = await extract_fields_with_llm(user_input, memory_context, conversation_history)
    # Shim: wrap into the old dict-of-FieldClassification format so old call sites don't crash
    result = {}
    for f in fields:
        try:
            result[f.key] = FieldClassification(
                raw_value=f.value,
                field_type="SCHEMA_FIELD",
                field_name=f.key,
                normalized_value=f.value,
                category="other",
                is_correction=f.is_correction,
            )
        except Exception:
            pass
    return result
