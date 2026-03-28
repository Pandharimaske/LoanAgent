"""
SQLite database operations for customer memory.
Two tables:
  customer_memory   — current field values (one row per customer)
  customer_changelog — full audit trail of every field change

changelog schema: customer_id | entity | old_val | old_timestamp | upd_val | timestamp
Only the last 15 days of changelog are surfaced to the agent (older kept for audit).
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
        logger.info("✅ customer_memory schema initialized")

    def init_changelog_schema(self) -> None:
        """
        Create customer_changelog table if it doesn't exist.
        Safe to call multiple times (idempotent).

        Schema:
            customer_id   — FK to customer_memory
            entity        — field name (e.g. 'monthly_income')
            old_val       — previous value as text (NULL on first write)
            old_timestamp — when old_val was last set (NULL on first write)
            upd_val       — new value as text
            timestamp     — when this change was recorded (UTC ISO-8601)
        """
        self._ensure_connection()
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS customer_changelog (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id   TEXT    NOT NULL,
                entity        TEXT    NOT NULL,
                old_val       TEXT,
                old_timestamp TEXT,
                upd_val       TEXT    NOT NULL,
                timestamp     TEXT    NOT NULL
            )
        """)
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_changelog_customer_entity "
            "ON customer_changelog(customer_id, entity, timestamp DESC)"
        )
        self.connection.commit()
        logger.info("✅ customer_changelog schema initialized")

    # --------------------------------------------------------- changelog

    def log_field_change(
        self,
        customer_id: str,
        entity: str,
        old_val: Any,
        old_timestamp: Optional[str],
        upd_val: Any,
    ) -> None:
        """
        Write one row to customer_changelog.
        Called automatically inside batch_update_fields and update_field_value.
        """
        self._ensure_connection()
        now = datetime.utcnow().isoformat()
        try:
            self.connection.execute(
                """
                INSERT INTO customer_changelog
                    (customer_id, entity, old_val, old_timestamp, upd_val, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    customer_id,
                    entity,
                    str(old_val) if old_val is not None else None,
                    old_timestamp,
                    str(upd_val),
                    now,
                ),
            )
            # Note: caller is responsible for commit
        except Exception as exc:
            logger.warning(f"⚠️  changelog write failed for {entity}: {exc}")

    def get_field_changelog(
        self,
        customer_id: str,
        entity: str,
        days: int = 15,
    ) -> List[Dict[str, Any]]:
        """
        Return changelog entries for a specific field, limited to the last `days` days.
        Ordered newest-first.

        Returns list of dicts:
            {entity, old_val, old_timestamp, upd_val, timestamp}
        """
        self._ensure_connection()
        cutoff = (
            datetime.utcnow()
            .replace(hour=0, minute=0, second=0, microsecond=0)
        )
        import datetime as dt
        cutoff = cutoff - dt.timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT entity, old_val, old_timestamp, upd_val, timestamp
            FROM   customer_changelog
            WHERE  customer_id = ?
              AND  entity = ?
              AND  timestamp >= ?
            ORDER BY timestamp DESC
            """,
            (customer_id, entity, cutoff_str),
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def get_all_recent_changelog(
        self,
        customer_id: str,
        days: int = 15,
        fields: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Return changelog for multiple fields (or all fields) in the last `days` days.
        Returns {entity: [rows...]} grouped by field name.

        Args:
            customer_id: Customer identifier
            days:        Look-back window (default 15)
            fields:      If provided, only fetch changelog for these specific fields.
                         If None/empty, fetch for all tracked fields.
        """
        self._ensure_connection()
        import datetime as dt
        cutoff = datetime.utcnow() - dt.timedelta(days=days)
        cutoff_str = cutoff.isoformat()

        cursor = self.connection.cursor()
        if fields:
            placeholders = ",".join("?" * len(fields))
            cursor.execute(
                f"""
                SELECT entity, old_val, old_timestamp, upd_val, timestamp
                FROM   customer_changelog
                WHERE  customer_id = ?
                  AND  entity IN ({placeholders})
                  AND  timestamp >= ?
                ORDER BY entity, timestamp DESC
                """,
                (customer_id, *fields, cutoff_str),
            )
        else:
            cursor.execute(
                """
                SELECT entity, old_val, old_timestamp, upd_val, timestamp
                FROM   customer_changelog
                WHERE  customer_id = ?
                  AND  timestamp >= ?
                ORDER BY entity, timestamp DESC
                """,
                (customer_id, cutoff_str),
            )

        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in cursor.fetchall():
            r = dict(row)
            result.setdefault(r["entity"], []).append(r)
        return result

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
        Update a single field value and log the change to customer_changelog.
        Ensures customer row exists first (no silent data loss on new customers).
        Returns True on success.
        """
        if field_name not in VALID_COLUMNS:
            logger.error(f"❌ Unknown field '{field_name}' — rejecting update")
            return False

        self.ensure_customer_exists(customer_id)
        self._ensure_connection()
        now = datetime.utcnow().isoformat()

        try:
            # Read old value + its timestamp for changelog
            cursor = self.connection.cursor()
            cursor.execute(
                f"SELECT {field_name}, last_updated FROM customer_memory WHERE customer_id=?",
                (customer_id,),
            )
            row = cursor.fetchone()
            old_val       = row[field_name] if row else None
            old_timestamp = row["last_updated"] if row else None

            self.connection.execute(
                f"UPDATE customer_memory SET {field_name}=?, last_updated=? WHERE customer_id=?",
                (value, now, customer_id),
            )
            # Log the change
            self.log_field_change(customer_id, field_name, old_val, old_timestamp, value)
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
        Reads old values before writing so they can be logged to changelog.
        Returns {field_name: success} for each field.
        """
        if not fields:
            return {}

        self.ensure_customer_exists(customer_id)
        self._ensure_connection()

        # Pre-read old values + last_updated for all fields we're about to change
        valid_fields = [f for f in fields if f in VALID_COLUMNS]
        old_values: Dict[str, Any]   = {}
        old_timestamps: Dict[str, str] = {}
        if valid_fields:
            try:
                cols = ", ".join(valid_fields) + ", last_updated"
                cursor = self.connection.cursor()
                cursor.execute(
                    f"SELECT {cols} FROM customer_memory WHERE customer_id=?",
                    (customer_id,),
                )
                row = cursor.fetchone()
                if row:
                    row_d = dict(row)
                    ts = row_d.get("last_updated")
                    for f in valid_fields:
                        old_values[f]     = row_d.get(f)
                        old_timestamps[f] = ts
            except Exception as exc:
                logger.warning(f"⚠️  Could not read old values for changelog: {exc}")

        results: Dict[str, bool] = {}
        now = datetime.utcnow().isoformat()

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
                        # Log change to changelog
                        self.log_field_change(
                            customer_id,
                            field_name,
                            old_values.get(field_name),
                            old_timestamps.get(field_name),
                            value,
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
        logger.info(f"💾 batch_update {customer_id}: {ok}/{len(results)} OK → changelog written")
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
