"""
Pydantic models for LoanAgent customer memory.
Simplified — no status columns, no version history.
application_status is the only status kept (business state, not data quality).
"""

from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class CustomerMemory(BaseModel):
    """
    Complete customer memory.
    Stores current values only — no per-field status flags.
    application_status tracks the loan application lifecycle only.
    """
    customer_id: str

    # --- Identity ---
    full_name: Optional[str] = None
    date_of_birth: Optional[str] = None   # ISO format: YYYY-MM-DD
    phone: Optional[str] = None

    # --- Address ---
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    pincode: Optional[str] = None

    # --- Employment ---
    employer_name: Optional[str] = None
    job_title: Optional[str] = None
    years_at_job: Optional[float] = None

    # --- Income & Financials ---
    monthly_income: Optional[float] = None
    income_type: Optional[str] = None     # "salaried" | "self_employed" | "rental"

    # --- Credit & Loans ---
    cibil_score: Optional[int] = None
    total_existing_emi_monthly: Optional[float] = None
    number_of_active_loans: Optional[int] = None

    # --- Loan Request ---
    requested_loan_type: Optional[str] = None      # "home" | "auto" | "personal"
    requested_loan_amount: Optional[float] = None
    requested_tenure_months: Optional[int] = None
    loan_purpose: Optional[str] = None

    # --- Co-Applicant ---
    coapplicant_name: Optional[str] = None
    coapplicant_relation: Optional[str] = None     # "spouse" | "sibling" | "parent"
    coapplicant_income: Optional[float] = None

    # --- Application (business-state, not data-quality) ---
    application_status: str = "incomplete"
    # Values: "incomplete" | "complete" | "processing" | "approved" | "rejected" | "on_hold"
    documents_submitted: Optional[str] = None      # comma-sep: "aadhar,pan,income_proof"

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
        phone="9876543210",
        city="Bangalore",
        state="Karnataka",
        employer_name="Tech Corp",
        job_title="Senior Engineer",
        years_at_job=5.5,
        monthly_income=45000.0,
        income_type="salaried",
        cibil_score=750,
        total_existing_emi_monthly=15000.0,
        requested_loan_type="home",
        requested_loan_amount=2500000.0,
        requested_tenure_months=240,
        coapplicant_name="Sunita Kumar",
        coapplicant_relation="spouse",
        coapplicant_income=30000.0,
        application_status="incomplete",
        created_at=now,
        last_updated=now,
    )


if __name__ == "__main__":
    memory = create_test_memory()
    print(memory.model_dump_json(indent=2))
