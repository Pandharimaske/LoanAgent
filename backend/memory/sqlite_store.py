"""
Simplified SQLite database operations.
Single table for customer memory - current values only.
No version history, no complex encryption, no unused tables.
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from config import SQLITE_PATH
from memory.models import CustomerMemory

logger = logging.getLogger(__name__)

# ============================================================================
# FIX #2 — FIELD → GROUP STATUS COLUMN MAPPING
#
# The schema uses GROUP status columns, NOT per-field _status columns.
# e.g.  "city"  must map to  "address_status",  NOT  "city_status" (non-existent).
# This dict is the single source of truth for all field→status mappings.
# ============================================================================

FIELD_TO_STATUS_COLUMN: Dict[str, Optional[str]] = {
    # Identity — each has its own status column
    "full_name":        "full_name_status",
    "date_of_birth":    "date_of_birth_status",
    "phone":            "phone_status",

    # Address — all four share address_status
    "address":  "address_status",
    "city":     "address_status",
    "state":    "address_status",
    "pincode":  "address_status",

    # Employment — all three share employment_status
    "employer_name":  "employment_status",
    "job_title":      "employment_status",
    "years_at_job":   "employment_status",

    # Income — both share income_status
    "monthly_income": "income_status",
    "income_type":    "income_status",

    # Credit — cibil has own; loans share loans_status
    "cibil_score":                "cibil_status",
    "total_existing_emi_monthly": "loans_status",
    "number_of_active_loans":     "loans_status",

    # Loan request — all share loan_request_status
    "requested_loan_type":     "loan_request_status",
    "requested_loan_amount":   "loan_request_status",
    "requested_tenure_months": "loan_request_status",
    "loan_purpose":            "loan_request_status",

    # Co-applicant — all share coapplicant_status
    "coapplicant_name":     "coapplicant_status",
    "coapplicant_relation": "coapplicant_status",
    "coapplicant_income":   "coapplicant_status",

    # Application — no separate status column
    "application_status":  None,
    "documents_submitted": None,
}

# Whitelist of valid column names — used to guard against SQL injection
VALID_COLUMNS: frozenset = frozenset([
    "customer_id",
    "full_name", "full_name_status",
    "date_of_birth", "date_of_birth_status",
    "phone", "phone_status",
    "address", "city", "state", "pincode", "address_status",
    "employer_name", "job_title", "years_at_job", "employment_status",
    "monthly_income", "income_status", "income_type",
    "cibil_score", "cibil_status",
    "total_existing_emi_monthly", "number_of_active_loans", "loans_status",
    "requested_loan_type", "requested_loan_amount",
    "requested_tenure_months", "loan_purpose", "loan_request_status",
    "coapplicant_name", "coapplicant_relation", "coapplicant_income", "coapplicant_status",
    "application_status", "documents_submitted",
    "created_at", "last_updated",
])


class MemoryDatabase:
    """Simplified SQLite database manager with robust field-update logic."""

    def __init__(self, db_path: str = SQLITE_PATH):
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------ core

    def connect(self) -> sqlite3.Connection:
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")    # better concurrency
        self.connection.execute("PRAGMA synchronous = NORMAL")  # safe + faster
        return self.connection

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def _ensure_connection(self):
        if not self.connection:
            self.connect()

    # ----------------------------------------------------------------- schema

    def init_schema(self):
        """Create customer_memory table + index if they don't exist."""
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_memory (
                customer_id TEXT PRIMARY KEY,

                -- Identity
                full_name TEXT,
                full_name_status TEXT DEFAULT 'pending',
                date_of_birth TEXT,
                date_of_birth_status TEXT DEFAULT 'pending',
                phone TEXT,
                phone_status TEXT DEFAULT 'pending',

                -- Address (all share address_status)
                address TEXT,
                city TEXT,
                state TEXT,
                pincode TEXT,
                address_status TEXT DEFAULT 'pending',

                -- Employment (all share employment_status)
                employer_name TEXT,
                job_title TEXT,
                years_at_job REAL,
                employment_status TEXT DEFAULT 'pending',

                -- Income (all share income_status)
                monthly_income REAL,
                income_status TEXT DEFAULT 'pending',
                income_type TEXT,

                -- Credit & Loans
                cibil_score INTEGER,
                cibil_status TEXT DEFAULT 'pending',
                total_existing_emi_monthly REAL,
                number_of_active_loans INTEGER,
                loans_status TEXT DEFAULT 'pending',

                -- Loan Request (all share loan_request_status)
                requested_loan_type TEXT,
                requested_loan_amount REAL,
                requested_tenure_months INTEGER,
                loan_purpose TEXT,
                loan_request_status TEXT DEFAULT 'pending',

                -- Co-Applicant (all share coapplicant_status)
                coapplicant_name TEXT,
                coapplicant_relation TEXT,
                coapplicant_income REAL,
                coapplicant_status TEXT DEFAULT 'pending',

                -- Application
                application_status TEXT DEFAULT 'incomplete',
                documents_submitted TEXT,

                -- Metadata
                created_at TEXT NOT NULL,
                last_updated TEXT NOT NULL
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_customer_updated ON customer_memory(last_updated)"
        )
        self.connection.commit()
        logger.info("✅ Database schema initialized")

    # --------------------------------------------------------------- helpers

    def ensure_customer_exists(self, customer_id: str) -> bool:
        """
        FIX #4 — INSERT a skeleton row for new customers before any UPDATE.
        Without this, UPDATE silently affects 0 rows and data is lost.
        Returns True if a new row was created, False if it already existed.
        """
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT 1 FROM customer_memory WHERE customer_id = ?", (customer_id,)
        )
        if cursor.fetchone():
            return False  # already exists — nothing to do

        now = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO customer_memory (customer_id, created_at, last_updated) VALUES (?,?,?)",
            (customer_id, now, now),
        )
        self.connection.commit()
        logger.info(f"🆕 Created skeleton row for new customer {customer_id}")
        return True

    # ------------------------------------------------------------------ CRUD

    def save_customer_memory(self, memory: CustomerMemory) -> None:
        """Full INSERT OR REPLACE for a CustomerMemory object."""
        self._ensure_connection()
        now = datetime.now().isoformat()
        self.connection.execute("""
            INSERT OR REPLACE INTO customer_memory (
                customer_id,
                full_name, full_name_status,
                date_of_birth, date_of_birth_status,
                phone, phone_status,
                address, city, state, pincode, address_status,
                employer_name, job_title, years_at_job, employment_status,
                monthly_income, income_status, income_type,
                cibil_score, cibil_status,
                total_existing_emi_monthly, number_of_active_loans, loans_status,
                requested_loan_type, requested_loan_amount,
                requested_tenure_months, loan_purpose, loan_request_status,
                coapplicant_name, coapplicant_relation, coapplicant_income, coapplicant_status,
                application_status, documents_submitted,
                created_at, last_updated
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            memory.customer_id,
            memory.full_name, memory.full_name_status,
            memory.date_of_birth, memory.date_of_birth_status,
            memory.phone, memory.phone_status,
            memory.address, memory.city, memory.state, memory.pincode, memory.address_status,
            memory.employer_name, memory.job_title, memory.years_at_job, memory.employment_status,
            memory.monthly_income, memory.income_status, memory.income_type,
            memory.cibil_score, memory.cibil_status,
            memory.total_existing_emi_monthly, memory.number_of_active_loans, memory.loans_status,
            memory.requested_loan_type, memory.requested_loan_amount,
            memory.requested_tenure_months, memory.loan_purpose, memory.loan_request_status,
            memory.coapplicant_name, memory.coapplicant_relation,
            memory.coapplicant_income, memory.coapplicant_status,
            memory.application_status, memory.documents_submitted,
            memory.created_at.isoformat(), now,
        ))
        self.connection.commit()
        logger.info(f"✅ Saved memory for {memory.customer_id}")

    def load_customer_memory(self, customer_id: str) -> Optional[CustomerMemory]:
        """Load full CustomerMemory for a customer. Returns None if not found."""
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM customer_memory WHERE customer_id = ?", (customer_id,))
        row = cursor.fetchone()
        if not row:
            logger.debug(f"No memory row found for {customer_id}")
            return None

        data = dict(row)
        data["created_at"]   = datetime.fromisoformat(data["created_at"])
        data["last_updated"] = datetime.fromisoformat(data["last_updated"])
        return CustomerMemory(**data)

    def get_confirmed_facts(self, customer_id: str) -> Dict[str, Any]:
        """
        Return nested dict of ONLY confirmed facts (status == 'confirmed').
        Used by load_memory node for context injection.
        """
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM customer_memory WHERE customer_id = ?", (customer_id,))
        row = cursor.fetchone()
        if not row:
            return {}

        data = dict(row)

        field_groups = {
            "identity": [
                ("full_name",     "full_name_status"),
                ("date_of_birth", "date_of_birth_status"),
                ("phone",         "phone_status"),
            ],
            "address": [
                ("address", "address_status"),
                ("city",    "address_status"),
                ("state",   "address_status"),
                ("pincode", "address_status"),
            ],
            "employment": [
                ("employer_name", "employment_status"),
                ("job_title",     "employment_status"),
                ("years_at_job",  "employment_status"),
            ],
            "income": [
                ("monthly_income", "income_status"),
                ("income_type",    "income_status"),
            ],
            "credit": [
                ("cibil_score",                "cibil_status"),
                ("total_existing_emi_monthly", "loans_status"),
                ("number_of_active_loans",     "loans_status"),
            ],
            "loan_request": [
                ("requested_loan_type",     "loan_request_status"),
                ("requested_loan_amount",   "loan_request_status"),
                ("requested_tenure_months", "loan_request_status"),
                ("loan_purpose",            "loan_request_status"),
            ],
            "coapplicant": [
                ("coapplicant_name",     "coapplicant_status"),
                ("coapplicant_relation", "coapplicant_status"),
                ("coapplicant_income",   "coapplicant_status"),
            ],
        }

        confirmed: Dict[str, Any] = {"customer_id": customer_id}
        for group_key, fields in field_groups.items():
            group: Dict[str, Any] = {}
            for val_col, status_col in fields:
                if data.get(status_col) == "confirmed" and data.get(val_col) is not None:
                    group[val_col] = data[val_col]
            if group:
                confirmed[group_key] = group

        confirmed["application_status"] = data.get("application_status", "incomplete")
        docs = data.get("documents_submitted")
        if docs:
            confirmed["documents_submitted"] = docs.split(",")

        logger.info(f"✅ Confirmed facts for {customer_id}: {list(confirmed.keys())}")
        return confirmed

    def get_all_facts(self, customer_id: str) -> Dict[str, Any]:
        """
        Return ALL non-null value fields (pending + confirmed).
        Used for mismatch detection — compares against everything stored,
        not just confirmed.
        """
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM customer_memory WHERE customer_id = ?", (customer_id,))
        row = cursor.fetchone()
        if not row:
            return {}

        data = dict(row)
        # Remove metadata cols and status cols; keep value cols only
        exclude = {"created_at", "last_updated", "customer_id"}
        exclude.update(k for k in data if k.endswith("_status"))
        return {k: v for k, v in data.items() if k not in exclude and v is not None}

    def update_field_value(
        self,
        customer_id: str,
        field_name: str,
        value: Any,
        status: str = "pending",
    ) -> bool:
        """
        FIX #2 — Update a single field using the correct group-status column.
        FIX #4 — Ensures customer row exists before UPDATE (no silent data loss).

        Returns True on success.
        """
        if field_name not in VALID_COLUMNS:
            logger.error(f"❌ Unknown field '{field_name}' — rejecting update")
            return False

        # Guarantee the row exists (creates skeleton for new customers)
        self.ensure_customer_exists(customer_id)

        self._ensure_connection()
        now = datetime.now().isoformat()
        status_col = FIELD_TO_STATUS_COLUMN.get(field_name)

        try:
            if status_col and status_col in VALID_COLUMNS:
                self.connection.execute(
                    f"UPDATE customer_memory SET {field_name}=?, {status_col}=?, last_updated=? "
                    f"WHERE customer_id=?",
                    (value, status, now, customer_id),
                )
            else:
                self.connection.execute(
                    f"UPDATE customer_memory SET {field_name}=?, last_updated=? "
                    f"WHERE customer_id=?",
                    (value, now, customer_id),
                )
            self.connection.commit()
            logger.debug(f"✅ {customer_id} | {field_name}={value!r} status={status}")
            return True
        except sqlite3.OperationalError as exc:
            logger.error(f"❌ update_field_value({field_name}): {exc}")
            return False

    def batch_update_fields(
        self,
        customer_id: str,
        fields: Dict[str, Any],
        status: str = "pending",
    ) -> Dict[str, bool]:
        """
        Atomically update multiple fields in a single transaction.
        Returns {field_name: success} for each field.
        More efficient than calling update_field_value() in a loop.
        """
        if not fields:
            return {}

        # One-time row guard before entering the transaction
        self.ensure_customer_exists(customer_id)
        self._ensure_connection()

        results: Dict[str, bool] = {}
        now = datetime.now().isoformat()

        try:
            with self.connection:
                cursor = self.connection.cursor()
                for field_name, value in fields.items():
                    if field_name not in VALID_COLUMNS:
                        logger.warning(f"⚠️  Skipping unknown field '{field_name}'")
                        results[field_name] = False
                        continue

                    status_col = FIELD_TO_STATUS_COLUMN.get(field_name)
                    try:
                        if status_col and status_col in VALID_COLUMNS:
                            cursor.execute(
                                f"UPDATE customer_memory SET {field_name}=?, {status_col}=?, last_updated=? "
                                f"WHERE customer_id=?",
                                (value, status, now, customer_id),
                            )
                        else:
                            cursor.execute(
                                f"UPDATE customer_memory SET {field_name}=?, last_updated=? "
                                f"WHERE customer_id=?",
                                (value, now, customer_id),
                            )
                        results[field_name] = True
                    except sqlite3.OperationalError as exc:
                        logger.error(f"❌ batch field {field_name}: {exc}")
                        results[field_name] = False
        except Exception as exc:
            logger.error(f"❌ batch_update_fields transaction failed: {exc}")
            for f in fields:
                results.setdefault(f, False)

        ok = sum(1 for v in results.values() if v)
        logger.info(f"💾 batch_update {customer_id}: {ok}/{len(results)} OK")
        return results

    def update_field_status(
        self, customer_id: str, status_column: str, new_status: str
    ) -> None:
        """Directly update a status column (e.g. promote a group to 'confirmed')."""
        if status_column not in VALID_COLUMNS:
            logger.error(f"❌ Unknown status column '{status_column}'")
            return
        self._ensure_connection()
        now = datetime.now().isoformat()
        self.connection.execute(
            f"UPDATE customer_memory SET {status_column}=?, last_updated=? WHERE customer_id=?",
            (new_status, now, customer_id),
        )
        self.connection.commit()
        logger.info(f"✅ {status_column} → {new_status} for {customer_id}")

    def delete_customer(self, customer_id: str) -> None:
        self._ensure_connection()
        self.connection.execute(
            "DELETE FROM customer_memory WHERE customer_id=?", (customer_id,)
        )
        self.connection.commit()
        logger.info(f"🗑️  Deleted memory for {customer_id}")

    def list_all_customers(self) -> List[str]:
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("SELECT customer_id FROM customer_memory ORDER BY last_updated DESC")
        return [row[0] for row in cursor.fetchall()]

    # --------------------------------------------------------- context manager

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *_):
        self.close()


# ============================================================================
# QUICK SMOKE TEST
# ============================================================================

def test_simplified_db():
    from memory.models import create_test_memory

    db = MemoryDatabase(db_path=":memory:")
    db.connect()
    db.init_schema()

    memory = create_test_memory()
    db.save_customer_memory(memory)
    loaded = db.load_customer_memory("RAJESH_001")
    assert loaded.full_name == "Rajesh Kumar", "Load failed"

    # Test status-column mapping (city → address_status, not city_status)
    ok = db.update_field_value("RAJESH_001", "city", "Mumbai", "pending")
    assert ok, "update_field_value failed for city"

    ok = db.update_field_value("RAJESH_001", "employer_name", "NewCorp", "pending")
    assert ok, "update_field_value failed for employer_name"

    # Test new customer INSERT guard
    ok = db.update_field_value("BRAND_NEW_001", "full_name", "New User", "pending")
    assert ok, "update_field_value failed for new customer"
    new_cust = db.load_customer_memory("BRAND_NEW_001")
    assert new_cust and new_cust.full_name == "New User", "New customer not saved"

    # Test batch update
    results = db.batch_update_fields("RAJESH_001", {
        "city": "Pune",
        "monthly_income": 65000,
        "cibil_score": 790,
    })
    assert all(results.values()), f"Batch failed: {results}"

    facts = db.get_confirmed_facts("RAJESH_001")
    assert "customer_id" in facts

    all_facts = db.get_all_facts("RAJESH_001")
    assert "monthly_income" in all_facts

    db.close()
    print("✅ All sqlite_store tests passed")


if __name__ == "__main__":
    test_simplified_db()
