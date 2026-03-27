"""
Simplified Pydantic models for LoanAgent memory system.
Stores current values only - no enums, no version history.
"""

from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


# ============================================================================
# MAIN MEMORY MODEL (SIMPLIFIED - CURRENT VALUES ONLY)
# ============================================================================


class CustomerMemory(BaseModel):
    """
    Complete customer memory - simplified.
    Stores current values only with status (pending/confirmed).
    No enums, no version history, no complexity.
    """
    customer_id: str
    
    # --- Identity ---
    full_name: Optional[str] = None
    full_name_status: str = "pending"  # "pending" or "confirmed"
    date_of_birth: Optional[str] = None  # ISO format
    date_of_birth_status: str = "pending"
    phone: Optional[str] = None
    phone_status: str = "pending"
    
    # --- Address ---
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None
    address_status: str = "pending"
    
    # --- Employment ---
    employer_name: Optional[str] = None
    job_title: Optional[str] = None
    years_at_job: Optional[float] = None
    employment_status: str = "pending"
    
    # --- Income & Financials ---
    monthly_income: Optional[float] = None
    income_status: str = "pending"
    income_type: Optional[str] = None  # "salaried", "self_employed", "rental"
    
    # --- Credit & Loans ---
    cibil_score: Optional[int] = None
    cibil_status: str = "pending"
    total_existing_emi_monthly: Optional[float] = None
    number_of_active_loans: Optional[int] = None
    loans_status: str = "pending"
    
    # --- Loan Request ---
    requested_loan_type: Optional[str] = None  # "home", "auto", "personal"
    requested_loan_amount: Optional[float] = None
    requested_tenure_months: Optional[int] = None
    loan_purpose: Optional[str] = None
    loan_request_status: str = "pending"
    
    # --- Co-Applicant ---
    coapplicant_name: Optional[str] = None
    coapplicant_relation: Optional[str] = None  # "spouse", "sibling", "parent"
    coapplicant_income: Optional[float] = None
    coapplicant_status: str = "pending"
    
    # --- Application ---
    application_status: str = "incomplete"  # "incomplete", "complete", "processing", "approved", "rejected", "on_hold"
    documents_submitted: Optional[str] = None  # Comma-separated: "aadhar,pan,income_proof"
    
    # --- Metadata ---
    created_at: datetime
    last_updated: datetime
    
    model_config = ConfigDict()


# ============================================================================
# TEST DATA
# ============================================================================


def create_test_memory() -> CustomerMemory:
    """Create test memory record (Rajesh scenario)."""
    now = datetime.now()
    
    return CustomerMemory(
        customer_id="RAJESH_001",
        full_name="Rajesh Kumar",
        full_name_status="confirmed",
        phone="9876543210",
        phone_status="confirmed",
        city="Bangalore",
        state="Karnataka",
        address_status="confirmed",
        employer_name="Tech Corp",
        job_title="Senior Engineer",
        years_at_job=5.5,
        employment_status="confirmed",
        monthly_income=45000,
        income_status="confirmed",
        income_type="salaried",
        cibil_score=750,
        cibil_status="pending",
        total_existing_emi_monthly=15000,
        loans_status="confirmed",
        requested_loan_type="home",
        requested_loan_amount=2500000,
        requested_tenure_months=240,
        loan_request_status="confirmed",
        coapplicant_name="Sunita Kumar",
        coapplicant_relation="spouse",
        coapplicant_income=30000,
        coapplicant_status="pending",
        application_status="incomplete",
        created_at=now,
        last_updated=now,
    )


if __name__ == "__main__":
    memory = create_test_memory()
    print(memory.model_dump_json(indent=2))
