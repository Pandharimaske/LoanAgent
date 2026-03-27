"""
LangGraph Node Implementations — Orchestrator & Re-exports

This module orchestrates node imports from specialized modules:
- core_nodes: Infrastructure nodes (check_token_threshold, load_memory, router, end_session)
- handlers: Action handlers (handle_memory_update, handle_mismatch_confirmation, handle_query, handle_general)
- schemas: Pydantic models for structured outputs
- helpers: LLM-based utility functions

Provides backward compatibility for imports from this single module.
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# ============================================================================
# RE-EXPORT SCHEMAS
# ============================================================================
from agent.schemas import (
    ConflictDetail,
    ConflictExtractionResult,
    FieldClassification,
    FieldClassificationResult,
    ExtractedEntity,
    EntityExtractionResult,
    SchemaFieldValidator,
    RouterDecision,
)

# ============================================================================
# RE-EXPORT HELPERS
# ============================================================================
from agent.helpers import (
    extract_conflicts_with_llm,
    classify_fields_with_llm,
)

# ============================================================================
# RE-EXPORT CORE NODES
# ============================================================================
from agent.core_nodes import (
    check_token_threshold,
    load_memory,
    router,
    end_session,
)

# ============================================================================
# RE-EXPORT HANDLERS
# ============================================================================
from agent.handlers import (
    handle_memory_update,
    handle_mismatch_confirmation,
    handle_query,
    handle_general,
)

logger = logging.getLogger(__name__)


__all__ = [
    # Schemas
    "ConflictDetail",
    "ConflictExtractionResult",
    "FieldClassification",
    "FieldClassificationResult",
    "ExtractedEntity",
    "EntityExtractionResult",
    "SchemaFieldValidator",
    "RouterDecision",
    # Helpers
    "extract_conflicts_with_llm",
    "classify_fields_with_llm",
    # Core nodes
    "check_token_threshold",
    "load_memory",
    "router",
    "end_session",
    # Handlers
    "handle_memory_update",
    "handle_mismatch_confirmation",
    "handle_query",
    "handle_general",
]
