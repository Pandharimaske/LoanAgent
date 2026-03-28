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

    model_config = ConfigDict(
        # Silently coerce compatible types (e.g. "750" → int for cibil_score)
        coerce_numbers_to_str=False,
    )

    # ──────────────────────────────────────────────
    # Field validators
    # ──────────────────────────────────────────────

    @classmethod
    def _parse_date(cls, v: object) -> Optional[str]:
        """Normalize any date string → YYYY-MM-DD (Indian convention DD/MM/YYYY)."""
        import re
        if v is None:
            return None
        raw = str(v).strip()
        if not raw:
            return None
        # Already ISO
        if re.match(r'^\d{4}-\d{2}-\d{2}$', raw):
            try:
                from datetime import date as _d
                _d.fromisoformat(raw)
                return raw
            except ValueError:
                pass
        # python-dateutil
        try:
            from dateutil import parser as du
            return du.parse(raw, dayfirst=True, yearfirst=False).strftime("%Y-%m-%d")
        except Exception:
            pass
        # Manual DD-MM-YYYY / DD/MM/YYYY / DD.MM.YYYY
        try:
            parts = re.split(r'[-/.]', raw)
            if len(parts) == 3:
                d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
                from datetime import date as _d
                return _d(y, m, d).strftime("%Y-%m-%d")
        except Exception:
            pass
        return None  # unparseable — will be skipped

    # Individual field validators using Pydantic v2 @field_validator
    from pydantic import field_validator

    @field_validator("date_of_birth", mode="before")
    @classmethod
    def normalize_dob(cls, v):
        return cls._parse_date(v)

    @field_validator("cibil_score", mode="before")
    @classmethod
    def check_cibil(cls, v):
        if v is None:
            return v
        score = int(float(str(v)))
        if not (300 <= score <= 900):
            raise ValueError(f"cibil_score {score} out of range 300-900")
        return score

    @field_validator("monthly_income", "total_existing_emi_monthly",
                     "coapplicant_income", "requested_loan_amount", mode="before")
    @classmethod
    def positive_float(cls, v):
        if v is None:
            return v
        val = float(str(v).replace(",", "").replace("₹", "").strip())
        if val < 0:
            raise ValueError(f"Value must be non-negative, got {val}")
        return val

    @field_validator("requested_tenure_months", "number_of_active_loans", mode="before")
    @classmethod
    def positive_int(cls, v):
        if v is None:
            return v
        val = int(float(str(v)))
        if val < 0:
            raise ValueError(f"Value must be non-negative, got {val}")
        return val

    @field_validator("years_at_job", mode="before")
    @classmethod
    def non_neg_float(cls, v):
        if v is None:
            return v
        return max(0.0, float(str(v)))

    @field_validator("income_type", mode="before")
    @classmethod
    def normalize_income_type(cls, v):
        if v is None:
            return v
        mapping = {"salaried": "salaried", "self employed": "self_employed",
                   "self_employed": "self_employed", "selfemployed": "self_employed",
                   "rental": "rental", "business": "self_employed", "freelance": "self_employed"}
        return mapping.get(str(v).lower().strip(), str(v).lower().strip())

    @field_validator("requested_loan_type", mode="before")
    @classmethod
    def normalize_loan_type(cls, v):
        if v is None:
            return v
        mapping = {"home": "home", "house": "home", "housing": "home",
                   "auto": "auto", "car": "auto", "vehicle": "auto",
                   "personal": "personal", "business": "business",
                   "education": "education", "gold": "gold"}
        return mapping.get(str(v).lower().strip(), str(v).lower().strip())

    # ──────────────────────────────────────────────
    # Helper: validate a raw partial dict of LLM-extracted fields
    # ──────────────────────────────────────────────

    @classmethod
    def validate_partial(cls, raw_fields: dict) -> tuple[dict, dict]:
        """
        Attempt to build a CustomerMemory from a partial dict of extracted fields.

        Only fields that exist on the model are validated. Fields that fail
        validation are collected as errors and excluded from the output.

        Returns:
            (valid_fields: dict, errors: dict)
            valid_fields — coerced, validated values ready to write to SQLite
            errors       — {field_name: error_message} for skipped fields
        """
        from datetime import datetime
        now = datetime.now()

        valid: dict = {}
        errors: dict = {}

        model_fields = cls.model_fields.keys()

        for field, value in raw_fields.items():
            if field not in model_fields:
                # Not a model field — caller should route to ChromaDB
                errors[field] = "not a model field"
                continue
            try:
                # Validate a single field by building a minimal model instance
                # with just that field + required fields
                test_obj = cls.model_validate({
                    "customer_id": "_validate_",
                    "created_at": now,
                    "last_updated": now,
                    field: value,
                })
                coerced = getattr(test_obj, field)
                if coerced is not None:
                    valid[field] = coerced
            except Exception as exc:
                errors[field] = str(exc)

        return valid, errors



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
