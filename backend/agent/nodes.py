"""
LangGraph Node re-exports.

Single import surface for graph.py — pulls from core_nodes and handlers.
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Schemas
from agent.schemas import (
    ExtractionResult,
    ExtractedField,
    RouterDecision,
)

# Helpers
from agent.helpers import (
    extract_fields_with_llm,
    format_conversation_history,
)

# Core nodes
from agent.core_nodes import (
    check_token_threshold,
    load_memory,
    router,
    end_session,
)

# Handlers
from agent.handlers import (
    extract_memory_node,
    handle_save_confirmation,
    handle_mismatch_confirmation,
    handle_query,
    handle_general,
)

logger = logging.getLogger(__name__)

__all__ = [
    # Schemas
    "ExtractionResult",
    "ExtractedField",
    "RouterDecision",
    # Helpers
    "extract_fields_with_llm",
    "format_conversation_history",
    # Core nodes
    "check_token_threshold",
    "load_memory",
    "router",
    "end_session",
    # Handlers
    "extract_memory_node",
    "handle_save_confirmation",
    "handle_mismatch_confirmation",
    "handle_query",
    "handle_general",
]
