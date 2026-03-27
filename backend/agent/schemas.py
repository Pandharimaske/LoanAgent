"""
Pydantic schemas for structured LLM outputs and validation.

Organized by concern:
- Field Classification : FieldClassification, FieldClassificationResult
- Entity Extraction    : ExtractedEntity, EntityExtractionResult
- Schema Validation    : SchemaFieldValidator
- Routing              : RouterDecision
"""

from typing import Literal, Optional, Union, List
from pydantic import BaseModel, Field

# Ollama's JSON schema validator rejects `Any` (serialized as `{}` with no type).
# Use a concrete Union so Ollama receives a valid `anyOf` constraint.
ScalarValue = Union[str, float, int, bool, None]


# ============================================================================
# FIELD CLASSIFICATION SCHEMAS
# ============================================================================

class FieldClassification(BaseModel):
    """Classification of a single piece of information from the user."""
    raw_value: str = Field(..., description="Original customer input text")
    field_type: Literal["SCHEMA_FIELD", "CONTEXTUAL_INFO"] = Field(
        ..., description="SCHEMA_FIELD if it maps to a DB column, CONTEXTUAL_INFO otherwise"
    )
    field_name: str = Field(
        ..., description="Exact DB column name if SCHEMA_FIELD, else a short semantic label"
    )
    normalized_value: ScalarValue = Field(
        default=None, description="Cleaned/coerced value ready for DB storage"
    )
    category: str = Field(..., description="Topic group: income | employment | personal | loan | other")
    is_correction: bool = Field(
        default=False,
        description=(
            "True ONLY when the user is explicitly correcting or updating a previously "
            "stated value (e.g. 'actually my income is 60k, not 50k'). False for first-time statements."
        ),
    )


class FieldClassificationResult(BaseModel):
    """Full LLM response for field classification."""
    classifications: List[FieldClassification] = Field(
        default_factory=list, description="One entry per extracted piece of information"
    )
    summary: str = Field(..., description="One-line summary of what was extracted")


# ============================================================================
# ENTITY EXTRACTION SCHEMAS  (used by entity extraction prompt — legacy)
# ============================================================================

class ExtractedEntity(BaseModel):
    """Single extracted entity from customer input."""
    raw_value: str = Field(..., description="Exact text from customer")
    normalized_value: ScalarValue = Field(..., description="Cleaned/processed value")
    value_type: str = Field(..., description="Data type: string | number | date | boolean")
    category: str = Field(
        ...,
        description="income | employment | personal | communication | concern | intent | other",
    )
    storage_target: str = Field(..., description="SQLite | ChromaDB")
    confidence: float = Field(..., description="Confidence 0.0–1.0")


class EntityExtractionResult(BaseModel):
    """LLM entity extraction result."""
    entities: List[ExtractedEntity] = Field(default_factory=list)
    summary: str = Field(..., description="Summary of extraction")


# ============================================================================
# SCHEMA FIELD VALIDATION  (Pydantic-level range checks)
# ============================================================================

class SchemaFieldValidator(BaseModel):
    """Range-validated schema fields — used for pre-write sanity checks."""
    monthly_income: Optional[float] = Field(None, ge=0, le=10_000_000)
    cibil_score: Optional[int] = Field(None, ge=300, le=900)
    number_of_active_loans: Optional[int] = Field(None, ge=0, le=50)
    requested_loan_amount: Optional[float] = Field(None, ge=0, le=100_000_000)

    class Config:
        validate_assignment = True


# ============================================================================
# ROUTER SCHEMA
# ============================================================================

class RouterDecision(BaseModel):
    """
    Structured routing decision produced by the LLM router.

    IMPORTANT — reduced option set:
    Mismatch detection and HITL save-confirmation are handled PROGRAMMATICALLY
    by extract_memory_node before the LLM router runs.  The LLM only ever needs
    to decide between two response modes:

      • handle_query   — user is asking a question that needs an answer
      • handle_general — greeting, statement, acknowledgment, small talk
    """

    next_handler: Literal[
        "handle_query",
        "handle_general",
    ] = Field(
        ...,
        description=(
            "handle_query  → user asked a question requiring an answer; "
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
