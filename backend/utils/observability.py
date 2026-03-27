"""
LangSmith observability and tracing configuration.
Initializes LangSmith for monitoring and debugging LLM interactions.
"""

import os
import logging
from config import LANGCHAIN_API_KEY, LANGSMITH_TRACING_V2, LANGSMITH_PROJECT

logger = logging.getLogger(__name__)


def init_langsmith():
    """
    Initialize LangSmith tracing for observability.
    
    Environment variables used:
    - LANGCHAIN_API_KEY: API key for LangSmith (required for tracing)
    - LANGSMITH_TRACING_V2: Enable/disable tracing (default: true)
    - LANGSMITH_PROJECT: Project name for organizing traces (default: LoanAgent)
    """
    
    try:
        # Set environment variables for LangSmith
        if LANGSMITH_TRACING_V2:
            os.environ["LANGSMITH_TRACING_V2"] = "true"
            os.environ["LANGSMITH_PROJECT"] = LANGSMITH_PROJECT
            
            if LANGCHAIN_API_KEY:
                os.environ["LANGCHAIN_API_KEY"] = LANGCHAIN_API_KEY
                logger.info(f"✅ LangSmith tracing enabled - Project: {LANGSMITH_PROJECT}")
            else:
                logger.warning(
                    "⚠️  LangSmith tracing enabled but LANGCHAIN_API_KEY not set. "
                    "Traces will not be sent to LangSmith dashboard. "
                    "Set LANGCHAIN_API_KEY in .env to enable."
                )
        else:
            logger.info("ℹ️  LangSmith tracing disabled")
            
    except Exception as e:
        logger.error(f"❌ Error initializing LangSmith: {str(e)}")


def get_langsmith_status() -> dict:
    """
    Get current LangSmith configuration status.
    
    Returns:
        dict: Status information about LangSmith configuration
    """
    return {
        "enabled": LANGSMITH_TRACING_V2,
        "project": LANGSMITH_PROJECT,
        "api_key_set": bool(LANGCHAIN_API_KEY),
        "api_key_preview": LANGCHAIN_API_KEY[:10] + "..." if LANGCHAIN_API_KEY else "NOT SET",
    }
