"""
Pydantic models for LoanAgent memory system.
Defines all data structures with versioning, history, and status tracking.
"""

from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List, Any, Dict
from datetime import datetime
from enum import Enum
import hashlib
import json


# ============================================================================
# ENUMS
# ============================================================================


class MemoryStatus(str, Enum):
    """Status of a memory field value."""
    PENDING = "pending"           # Mentioned but not confirmed
    CONFIRMED = "confirmed"       # Explicitly confirmed by user
    SUPERSEDED = "superseded"     # Replaced by new confirmed value
    RETRACTED = "retracted"       # User said this was wrong


class ApplicationStatus(str, Enum):
    """Status of the loan application."""
    INCOMPLETE = "incomplete"         # Still gathering info
    COMPLETE = "complete"             # All required info collected
    PROCESSING = "processing"         # Under bank review
    APPROVED = "approved"
    REJECTED = "rejected"
    ON_HOLD = "on_hold"


# ============================================================================
# CORE MEMORY STRUCTURES
# ============================================================================


class EntityRecord(BaseModel):
    """A single value record with metadata and history tracking."""
    value: Any
    status: MemoryStatus = MemoryStatus.PENDING
    timestamp: datetime
    session_id: str
    confirmed_at: Optional[datetime] = None
    retracted_at: Optional[datetime] = None
    retracted_reason: Optional[str] = None

    model_config = ConfigDict(ser_json_timedelta="iso8601")


class FixedEntity(BaseModel):
    """
    Versioned entity with history.
    Current = latest value, history = all past values.
    """
    current: Optional[EntityRecord] = None
    history: List[EntityRecord] = []

    def add_value(
        self,
        value: Any,
        session_id: str,
        status: MemoryStatus = MemoryStatus.PENDING,
    ) -> None:
        """Add a new value and move current to history if exists."""
        if self.current:
            # Mark old value as SUPERSEDED before archiving
            if self.current.status == MemoryStatus.CONFIRMED:
                self.current.status = MemoryStatus.SUPERSEDED
            self.history.append(self.current)
        
        self.current = EntityRecord(
            value=value,
            status=status,
            timestamp=datetime.now(),
            session_id=session_id,
        )

    def confirm(self) -> None:
        """Confirm current value."""
        if self.current:
            self.current.status = MemoryStatus.CONFIRMED
            self.current.confirmed_at = datetime.now()

    def retract(self, reason: str = None) -> None:
        """Retract current value."""
        if self.current:
            self.current.status = MemoryStatus.RETRACTED
            self.current.retracted_at = datetime.now()
            self.current.retracted_reason = reason
            self.history.append(self.current)
            self.current = None


# ============================================================================
# NESTED ENTITIES
# ============================================================================


class CoApplicant(BaseModel):
    """Co-applicant information."""
    name: Optional[FixedEntity] = None
    relation: Optional[FixedEntity] = None  # spouse, sibling, parent
    income_monthly: Optional[FixedEntity] = None
    occupation: Optional[FixedEntity] = None


class Guarantor(BaseModel):
    """Guarantor information."""
    name: Optional[FixedEntity] = None
    relation: Optional[FixedEntity] = None  # father, mother, friend
    phone: Optional[FixedEntity] = None


class DocumentSubmission(BaseModel):
    """Submitted document record."""
    doc_type: str  # "id_proof", "address_proof", "income_proof", "bank_stmt"
    submitted_at: datetime
    status: str = "pending_review"  # pending_review | verified | rejected
    verification_notes: Optional[str] = None
    verified_by: Optional[str] = None
    verification_date: Optional[datetime] = None


class LoanRequest(BaseModel):
    """Loan application request details."""
    loan_type: Optional[FixedEntity] = None  # "home", "auto", "personal"
    loan_amount: Optional[FixedEntity] = None
    tenure_months: Optional[FixedEntity] = None
    purpose: Optional[FixedEntity] = None


class EmploymentHistory(BaseModel):
    """Single employment record."""
    employer_name: Optional[FixedEntity] = None
    designation: Optional[FixedEntity] = None
    monthly_income: Optional[FixedEntity] = None
    years_worked: Optional[FixedEntity] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_current: bool = True


# ============================================================================
# MAIN MEMORY MODELS (NON-PII)
# ============================================================================


class CustomerMemoryNonPII(BaseModel):
    """
    Non-sensitive customer data stored in plaintext.
    Encrypted in transit, not at rest.
    """
    customer_id: str
    
    # Income & Employment (plaintext - amounts are public-ish in context)
    monthly_income: Optional[FixedEntity] = None
    income_type: Optional[FixedEntity] = None  # "salaried", "self_employed", "rental"
    total_work_experience_years: Optional[FixedEntity] = None
    employment_history: List[EmploymentHistory] = []
    
    # Credit info (plaintext - scores are often discussed)
    cibil_score: Optional[FixedEntity] = None
    cibil_last_checked: Optional[datetime] = None
    total_existing_emi_monthly: Optional[FixedEntity] = None
    number_of_active_loans: Optional[FixedEntity] = None
    
    # Loan request
    loan_request: Optional[LoanRequest] = None
    
    # Documents submitted (plaintext - just types/dates, no content)
    documents_submitted: List[DocumentSubmission] = []
    
    # Application status
    application_status: ApplicationStatus = ApplicationStatus.INCOMPLETE
    is_active: bool = True
    
    # Metadata
    created_at: datetime
    last_updated: datetime
    
    model_config = ConfigDict(use_enum_values=True)


# ============================================================================
# MAIN MEMORY MODELS (PII - ENCRYPTED)
# ============================================================================


class CustomerMemoryPII(BaseModel):
    """
    Personal Identifiable Information stored encrypted.
    All fields are encrypted before SQLite persistence.
    Decrypted only when needed for agent context.
    """
    customer_id: str  # NOT encrypted, used as foreign key
    
    # Identity (encrypted)
    full_name: Optional[FixedEntity] = None
    date_of_birth: Optional[FixedEntity] = None
    gender: Optional[FixedEntity] = None
    marital_status: Optional[FixedEntity] = None
    
    # Document hashes (not encrypted - one-way hash of PAN, Aadhaar)
    pan_hash: Optional[str] = None  # SHA256(PAN) - for dedup, no reverse lookup
    aadhaar_hash: Optional[str] = None  # SHA256(Aadhaar) - for dedup
    
    # Contact (encrypted)
    primary_phone: Optional[FixedEntity] = None
    current_address: Optional[FixedEntity] = None
    city: Optional[FixedEntity] = None
    state: Optional[FixedEntity] = None
    pincode: Optional[FixedEntity] = None
    
    # Employment (encrypted)
    employer_name: Optional[FixedEntity] = None
    years_at_current_job: Optional[FixedEntity] = None
    
    # Relations (encrypted, repeatable)
    co_applicants: List[CoApplicant] = []
    guarantors: List[Guarantor] = []
    
    # Metadata
    created_at: datetime
    last_updated: datetime
    
    model_config = ConfigDict(ser_json_timedelta="iso8601")


# ============================================================================
# SESSION TRACKING
# ============================================================================


class SessionLog(BaseModel):
    """Single session record."""
    session_id: str
    customer_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    agent_id: Optional[str] = None
    
    # Conversation turns
    turns: List[Dict] = []  # [{"role": "user"/"assistant", "content": "...", "timestamp": "..."}]
    
    # Summary (generated by LLM after session ends)
    summary: Optional[str] = None
    
    model_config = ConfigDict(ser_json_timedelta="iso8601")


class FieldChangeLog(BaseModel):
    """Track every field change for audit trail."""
    id: Optional[int] = None  # Auto-increment in SQLite
    customer_id: str
    field_name: str
    old_value: Optional[str] = None  # May be encrypted
    new_value: Optional[str] = None  # May be encrypted
    changed_at: datetime
    session_id: str
    conflict_detected: bool = False
    user_confirmed: bool = False
    confirmation_timestamp: Optional[datetime] = None
    
    model_config = ConfigDict(ser_json_timedelta="iso8601")


# ============================================================================
# HELPER UTILITIES
# ============================================================================


def hash_pan(pan: str) -> str:
    """
    Hash a PAN number for deduplication without storing raw PAN.
    SHA256(PAN) -> cannot be reversed, but same PAN always hashes same.
    """
    return hashlib.sha256(pan.upper().strip().encode()).hexdigest()


def hash_aadhaar(aadhaar: str) -> str:
    """Hash an Aadhaar number (same security as PAN)."""
    return hashlib.sha256(aadhaar.strip().encode()).hexdigest()


def fixed_entity_to_dict(entity: Optional[FixedEntity]) -> Optional[str]:
    """
    Serialize FixedEntity to JSON string for storage.
    """
    if entity is None:
        return None
    return entity.model_dump_json()


def fixed_entity_from_dict(data: Optional[str]) -> Optional[FixedEntity]:
    """Deserialize FixedEntity from JSON string."""
    if data is None:
        return None
    return FixedEntity.model_validate_json(data)


# ============================================================================
# TEST DATA
# ============================================================================


def create_test_memory() -> tuple[CustomerMemoryNonPII, CustomerMemoryPII]:
    """Create test memory records (Rajesh scenario)."""
    now = datetime.now()
    
    # Non-PII
    nonpii = CustomerMemoryNonPII(
        customer_id="RAJESH_001",
        monthly_income=FixedEntity(
            current=EntityRecord(
                value=45000,
                status=MemoryStatus.CONFIRMED,
                timestamp=now,
                session_id="S1",
                confirmed_at=now,
            )
        ),
        income_type=FixedEntity(
            current=EntityRecord(
                value="salaried",
                status=MemoryStatus.CONFIRMED,
                timestamp=now,
                session_id="S1",
            )
        ),
        cibil_score=FixedEntity(
            current=EntityRecord(
                value=750,
                status=MemoryStatus.PENDING,
                timestamp=now,
                session_id="S1",
            )
        ),
        total_existing_emi_monthly=FixedEntity(
            current=EntityRecord(
                value=15000,
                status=MemoryStatus.CONFIRMED,
                timestamp=now,
                session_id="S1",
            )
        ),
        loan_request=LoanRequest(
            loan_amount=FixedEntity(
                current=EntityRecord(
                    value=2500000,  # 25 lakhs in rupees
                    status=MemoryStatus.CONFIRMED,
                    timestamp=now,
                    session_id="S1",
                )
            )
        ),
        created_at=now,
        last_updated=now,
    )
    
    # PII (encrypted in persistence)
    pii = CustomerMemoryPII(
        customer_id="RAJESH_001",
        full_name=FixedEntity(
            current=EntityRecord(
                value="Rajesh Kumar",
                status=MemoryStatus.CONFIRMED,
                timestamp=now,
                session_id="S1",
            )
        ),
        primary_phone=FixedEntity(
            current=EntityRecord(
                value="9876543210",
                status=MemoryStatus.CONFIRMED,
                timestamp=now,
                session_id="S1",
            )
        ),
        city=FixedEntity(
            current=EntityRecord(
                value="Bangalore",
                status=MemoryStatus.CONFIRMED,
                timestamp=now,
                session_id="S1",
            )
        ),
        co_applicants=[
            CoApplicant(
                name=FixedEntity(
                    current=EntityRecord(
                        value="Sunita Kumar",
                        status=MemoryStatus.CONFIRMED,
                        timestamp=now,
                        session_id="S1",
                    )
                ),
                relation=FixedEntity(
                    current=EntityRecord(
                        value="spouse",
                        status=MemoryStatus.CONFIRMED,
                        timestamp=now,
                        session_id="S1",
                    )
                ),
                income_monthly=FixedEntity(
                    current=EntityRecord(
                        value=30000,
                        status=MemoryStatus.PENDING,
                        timestamp=now,
                        session_id="S1",
                    )
                ),
            )
        ],
        created_at=now,
        last_updated=now,
    )
    
    return nonpii, pii


if __name__ == "__main__":
    nonpii, pii = create_test_memory()
    print("Non-PII:")
    print(nonpii.model_dump_json(indent=2))
    print("\nPII:")
    print(pii.model_dump_json(indent=2))
