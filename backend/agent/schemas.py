"""
Pydantic schemas for structured LLM outputs.

- ExtractionResult  : LLM extracts key-value pairs; routing (SQLite vs ChromaDB)
                      is decided in code by checking CustomerMemory.model_fields
- RouterDecision    : Routing signal from the LLM router node
"""

from typing import Literal, Optional, List
from pydantic import BaseModel, Field


# ============================================================================
# EXTRACTION SCHEMA  (replaces FieldClassification)
# ============================================================================

class ExtractedField(BaseModel):
    """
    A single piece of information extracted from the user's message.

    The LLM's ONLY job here is to extract facts and map them to the right
    field name where possible. The decision of WHERE to store (SQLite vs ChromaDB)
    is made in code by checking CustomerMemory.model_fields.
    """
    key: str = Field(
        ...,
        description=(
            "Exact CustomerMemory field name if this maps to a schema column "
            "(e.g. 'monthly_income', 'city', 'cibil_score'). "
            "Otherwise use a short descriptive label (e.g. 'loan_goal', 'concern')."
        ),
    )
    value: str = Field(
        ...,
        description="The raw value exactly as expressed by the customer.",
    )
    is_correction: bool = Field(
        default=False,
        description=(
            "True ONLY when the customer is explicitly correcting a previously "
            "stated value (e.g. 'actually my income is 60k, not 50k'). "
            "False for all first-time statements."
        ),
    )


class ExtractionResult(BaseModel):
    """Structured LLM response for the extraction step."""
    fields: List[ExtractedField] = Field(
        default_factory=list,
        description="All facts extracted from the customer statement. Extract everything — miss nothing.",
    )
    summary: str = Field(
        default="",
        description="One-line summary of what was extracted (for logging).",
    )


# ============================================================================
# ROUTER SCHEMA
# ============================================================================

class RouterDecision(BaseModel):
    """
    Structured routing decision produced by the LLM router.

    Mismatch detection and HITL save-confirmation are handled PROGRAMMATICALLY
    by extract_memory_node before the LLM router runs. The LLM only chooses
    between two response modes:

      • handle_query   — user is asking a question that needs an answer
      • handle_general — greeting, statement, acknowledgment, small talk
    """

    next_handler: Literal[
        "handle_query",
        "handle_general",
    ] = Field(
        ...,
        description=(
            "handle_query  → user asked a question requiring a factual answer; "
            "handle_general → greeting / statement / small-talk / acknowledgment"
        ),
    )
    reasoning: str = Field(..., description="One-line explanation of the routing decision")
    confidence: float = Field(..., description="Confidence score 0.0–1.0")

    class Config:
        json_schema_extra = {
            "example": {
                "next_handler": "handle_query",
                "reasoning": "User asked 'Am I eligible for a 25L loan?' — needs a factual answer.",
                "confidence": 0.95,
            }
        }
