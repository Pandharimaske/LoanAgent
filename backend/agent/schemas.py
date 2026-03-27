"""
Pydantic schemas for structured LLM outputs and validation.

Organized by concern:
- Conflict Detection: ConflictDetail, ConflictExtractionResult
- Field Classification: FieldClassification, FieldClassificationResult
- Entity Extraction: ExtractedEntity, EntityExtractionResult
- Schema Validation: SchemaFieldValidator
- Routing: RouterDecision
"""

from typing import Literal, Optional, Union
from pydantic import BaseModel, Field

# Ollama's JSON schema validator rejects `Any` (serialized as `{}` with no type).
# Use a concrete Union so Ollama receives a valid `anyOf` constraint.
ScalarValue = Union[str, float, int, bool, None]


# ============================================================================
# CONFLICT DETECTION SCHEMAS
# ============================================================================

class ConflictDetail(BaseModel):
    """Details of a single conflicting field."""
    field: str = Field(..., description="Field name that has conflict")
    old_value: ScalarValue = Field(..., description="Previously confirmed value")
    new_value: ScalarValue = Field(..., description="New value from customer")
    confidence: float = Field(..., description="Confidence of conflict detection (0.0-1.0)")
    explanation: str = Field(..., description="Why this conflict matters")


class ConflictExtractionResult(BaseModel):
    """LLM analysis result for conflict extraction."""
    has_conflicts: bool = Field(..., description="Whether any conflicts were found")
    conflicts: list[ConflictDetail] = Field(default_factory=list, description="List of conflicts detected")
    summary: str = Field(..., description="Summary of analysis")


# ============================================================================
# FIELD CLASSIFICATION SCHEMAS
# ============================================================================

class FieldClassification(BaseModel):
    """Classification of a single field/info."""
    raw_value: str = Field(..., description="Original customer input")
    field_type: Literal["SCHEMA_FIELD", "CONTEXTUAL_INFO"] = Field(..., description="SCHEMA_FIELD or CONTEXTUAL_INFO")
    field_name: str = Field(..., description="Schema field name if SCHEMA_FIELD, else semantic description")
    normalized_value: ScalarValue = Field(default=None, description="Normalized value for schema fields")
    category: str = Field(..., description="Category (income, employment, etc.)")
    is_correction: bool = Field(default=False, description="True if user is explicitly updating, correcting, or confirming a new value")


class FieldClassificationResult(BaseModel):
    """LLM field classification result."""
    classifications: list[FieldClassification] = Field(default_factory=list, description="Field classifications")
    summary: str = Field(..., description="Summary of classification")


# ============================================================================
# ENTITY EXTRACTION SCHEMAS
# ============================================================================

class ExtractedEntity(BaseModel):
    """Single extracted entity from customer input."""
    raw_value: str = Field(..., description="Exact text from customer")
    normalized_value: ScalarValue = Field(..., description="Cleaned/processed value")
    value_type: str = Field(..., description="Data type (string, number, date, etc.)")
    category: str = Field(..., description="income | employment | personal | communication | concern | intent | other")
    storage_target: str = Field(..., description="SQLite or ChromaDB")
    confidence: float = Field(..., description="Confidence 0.0-1.0")


class EntityExtractionResult(BaseModel):
    """LLM entity extraction result."""
    entities: list[ExtractedEntity] = Field(default_factory=list, description="Extracted entities")
    summary: str = Field(..., description="Summary of extraction")


# ============================================================================
# SCHEMA FIELD VALIDATION
# ============================================================================

class SchemaFieldValidator(BaseModel):
    """Pydantic validator for all schema fields with built-in validation rules."""
    monthly_income: Optional[float] = Field(None, ge=0, le=10000000, description="Monthly income in range [0, 10M]")
    cibil_score: Optional[int] = Field(None, ge=300, le=900, description="CIBIL score in range [300, 900]")
    total_work_experience_years: Optional[float] = Field(None, ge=0, le=60, description="Years of experience [0, 60]")
    number_of_active_loans: Optional[int] = Field(None, ge=0, le=50, description="Active loans count [0, 50]")
    loan_amount: Optional[float] = Field(None, ge=0, le=100000000, description="Loan amount in range [0, 100M]")
    
    class Config:
        validate_assignment = True


# ============================================================================
# ROUTER SCHEMA
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
