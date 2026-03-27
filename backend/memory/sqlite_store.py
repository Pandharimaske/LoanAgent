"""
SQLite database operations for customer memory.
Single table — current values only.
No status columns (removed to halve schema size).
application_status is the only non-value column kept (business lifecycle, not data quality).
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
# VALID COLUMNS whitelist — guards against SQL injection
# ============================================================================

VALID_COLUMNS: frozenset = frozenset([
    "customer_id",
    # Identity
    "full_name", "date_of_birth", "phone",
    # Address
    "address", "city", "state", "pincode",
    # Employment
    "employer_name", "job_title", "years_at_job",
    # Income
    "monthly_income", "income_type",
    # Credit
    "cibil_score", "total_existing_emi_monthly", "number_of_active_loans",
    # Loan Request
    "requested_loan_type", "requested_loan_amount",
    "requested_tenure_months", "loan_purpose",
    # Co-Applicant
    "coapplicant_name", "coapplicant_relation", "coapplicant_income",
    # Application
    "application_status", "documents_submitted",
    # Metadata
    "created_at", "last_updated",
])


class MemoryDatabase:
    """SQLite database manager for customer memory — no status columns."""

    def __init__(self, db_path: str = SQLITE_PATH):
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------ core

    def connect(self) -> sqlite3.Connection:
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")
        self.connection.execute("PRAGMA synchronous = NORMAL")
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
                date_of_birth TEXT,
                phone TEXT,

                -- Address
                address TEXT,
                city TEXT,
                state TEXT,
                pincode TEXT,

                -- Employment
                employer_name TEXT,
                job_title TEXT,
                years_at_job REAL,

                -- Income
                monthly_income REAL,
                income_type TEXT,

                -- Credit & Loans
                cibil_score INTEGER,
                total_existing_emi_monthly REAL,
                number_of_active_loans INTEGER,

                -- Loan Request
                requested_loan_type TEXT,
                requested_loan_amount REAL,
                requested_tenure_months INTEGER,
                loan_purpose TEXT,

                -- Co-Applicant
                coapplicant_name TEXT,
                coapplicant_relation TEXT,
                coapplicant_income REAL,

                -- Application (business state, not data quality)
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
        INSERT skeleton row for new customers before any UPDATE.
        Without this, UPDATE silently affects 0 rows and data is lost.
        Returns True if a new row was created, False if it already existed.
        """
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT 1 FROM customer_memory WHERE customer_id = ?", (customer_id,)
        )
        if cursor.fetchone():
            return False

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
                full_name, date_of_birth, phone,
                address, city, state, pincode,
                employer_name, job_title, years_at_job,
                monthly_income, income_type,
                cibil_score, total_existing_emi_monthly, number_of_active_loans,
                requested_loan_type, requested_loan_amount,
                requested_tenure_months, loan_purpose,
                coapplicant_name, coapplicant_relation, coapplicant_income,
                application_status, documents_submitted,
                created_at, last_updated
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            memory.customer_id,
            memory.full_name, memory.date_of_birth, memory.phone,
            memory.address, memory.city, memory.state, memory.pincode,
            memory.employer_name, memory.job_title, memory.years_at_job,
            memory.monthly_income, memory.income_type,
            memory.cibil_score, memory.total_existing_emi_monthly, memory.number_of_active_loans,
            memory.requested_loan_type, memory.requested_loan_amount,
            memory.requested_tenure_months, memory.loan_purpose,
            memory.coapplicant_name, memory.coapplicant_relation, memory.coapplicant_income,
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

    def get_all_facts_grouped(self, customer_id: str) -> Dict[str, Any]:
        """
        Return all non-null fields for a customer in a nested group structure.
        Used by load_memory node for context injection into the agent.

        Returns a dict like:
        {
            "customer_id": "...",
            "identity":    { "full_name": "...", "phone": "..." },
            "address":     { "city": "Mumbai", "state": "MH" },
            "employment":  { "employer_name": "TCS", ... },
            "income":      { "monthly_income": 50000, ... },
            "credit":      { "cibil_score": 750, ... },
            "loan_request":{ "requested_loan_amount": 2500000, ... },
            "coapplicant": { "coapplicant_name": "Sunita", ... },
            "application_status": "incomplete",
        }
        """
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM customer_memory WHERE customer_id = ?", (customer_id,))
        row = cursor.fetchone()
        if not row:
            return {}

        data = dict(row)

        field_groups = {
            "identity": ["full_name", "date_of_birth", "phone"],
            "address":  ["address", "city", "state", "pincode"],
            "employment": ["employer_name", "job_title", "years_at_job"],
            "income":   ["monthly_income", "income_type"],
            "credit":   ["cibil_score", "total_existing_emi_monthly", "number_of_active_loans"],
            "loan_request": [
                "requested_loan_type", "requested_loan_amount",
                "requested_tenure_months", "loan_purpose",
            ],
            "coapplicant": ["coapplicant_name", "coapplicant_relation", "coapplicant_income"],
        }

        result: Dict[str, Any] = {"customer_id": customer_id}
        for group_key, fields in field_groups.items():
            group: Dict[str, Any] = {}
            for field in fields:
                val = data.get(field)
                if val is not None:
                    group[field] = val
            if group:
                result[group_key] = group

        result["application_status"] = data.get("application_status", "incomplete")
        docs = data.get("documents_submitted")
        if docs:
            result["documents_submitted"] = docs.split(",")

        logger.info(f"✅ Customer facts for {customer_id}: {list(result.keys())}")
        return result

    def get_all_facts(self, customer_id: str) -> Dict[str, Any]:
        """
        Return ALL non-null value fields as a flat dict.
        Used for mismatch detection — compares against everything stored.
        """
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM customer_memory WHERE customer_id = ?", (customer_id,))
        row = cursor.fetchone()
        if not row:
            return {}

        data = dict(row)
        exclude = {"created_at", "last_updated", "customer_id"}
        return {k: v for k, v in data.items() if k not in exclude and v is not None}

    def update_field_value(
        self,
        customer_id: str,
        field_name: str,
        value: Any,
    ) -> bool:
        """
        Update a single field value.
        Ensures customer row exists first (no silent data loss on new customers).
        Returns True on success.
        """
        if field_name not in VALID_COLUMNS:
            logger.error(f"❌ Unknown field '{field_name}' — rejecting update")
            return False

        self.ensure_customer_exists(customer_id)
        self._ensure_connection()
        now = datetime.now().isoformat()

        try:
            self.connection.execute(
                f"UPDATE customer_memory SET {field_name}=?, last_updated=? WHERE customer_id=?",
                (value, now, customer_id),
            )
            self.connection.commit()
            logger.debug(f"✅ {customer_id} | {field_name}={value!r}")
            return True
        except sqlite3.OperationalError as exc:
            logger.error(f"❌ update_field_value({field_name}): {exc}")
            return False

    def batch_update_fields(
        self,
        customer_id: str,
        fields: Dict[str, Any],
    ) -> Dict[str, bool]:
        """
        Atomically update multiple fields in a single transaction.
        Returns {field_name: success} for each field.
        """
        if not fields:
            return {}

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
                    try:
                        cursor.execute(
                            f"UPDATE customer_memory SET {field_name}=?, last_updated=? WHERE customer_id=?",
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

    # Test simple field update (no status col)
    ok = db.update_field_value("RAJESH_001", "city", "Mumbai")
    assert ok, "update_field_value failed for city"

    # Test new customer INSERT guard
    ok = db.update_field_value("BRAND_NEW_001", "full_name", "New User")
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

    facts = db.get_all_facts_grouped("RAJESH_001")
    assert "customer_id" in facts
    assert "income" in facts

    all_facts = db.get_all_facts("RAJESH_001")
    assert "monthly_income" in all_facts

    db.close()
    print("✅ All sqlite_store tests passed")


if __name__ == "__main__":
    test_simplified_db()
