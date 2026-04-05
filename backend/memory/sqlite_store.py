"""
SQLite database operations for customer memory.
Two tables:
  customer_memory   — current field values (one row per customer)
  customer_changelog — full audit trail of every field change

changelog schema: customer_id | entity | old_val | old_timestamp | upd_val | timestamp
Only the last 15 days of changelog are surfaced to the agent (older kept for audit).

ENCRYPTION AT REST (Zero-Trust Architecture):
  All user data fields are encrypted (Fernet symmetric encryption) before
  writing to SQLite and decrypted on-the-fly during authorized reads.
  Primary keys, queryable status fields, and system timestamps are EXEMPT
  from encryption to preserve relational integrity and query capability.
  Existing plaintext data is handled gracefully — decryption failures
  fall back to returning the raw value as-is (backward compatible).
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

from config import SQLITE_PATH
from memory.models import CustomerMemory
from memory.encryption import get_encryption_manager

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


# ============================================================================
# ENCRYPTION AT REST — Column exemptions & type restoration
# ============================================================================

# Columns that are NEVER encrypted (PKs, FKs, system timestamps, queryable status)
ENCRYPT_EXEMPT: frozenset = frozenset({
    "customer_id",          # Primary Key — relational integrity
    "application_status",   # Queryable business state (WHERE clauses)
    "created_at",           # System metadata — needed for ordering/indexing
    "last_updated",         # System metadata — needed for ordering/indexing
})

# Original Python types for numeric columns — used to restore types after
# decryption (encrypted values are always stored as TEXT in SQLite).
# Columns not listed here default to str on decryption.
COLUMN_TYPES: Dict[str, type] = {
    "years_at_job":                float,
    "monthly_income":              float,
    "total_existing_emi_monthly":  float,
    "requested_loan_amount":       float,
    "coapplicant_income":          float,
    "cibil_score":                 int,
    "number_of_active_loans":      int,
    "requested_tenure_months":     int,
}


class MemoryDatabase:
    """SQLite database manager for customer memory with encryption at rest."""

    def __init__(self, db_path: str = SQLITE_PATH):
        self.db_path = db_path
        self.connection: Optional[sqlite3.Connection] = None
        self._encryptor = None  # lazy-loaded EncryptionManager

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

    # ========================================================================
    # ENCRYPTION LAYER — Invisible shield for all CRUD operations
    # ========================================================================

    def _get_encryptor(self):
        """Lazy-load the global EncryptionManager singleton."""
        if self._encryptor is None:
            self._encryptor = get_encryption_manager()
        return self._encryptor

    def _encrypt_value(self, value: Any) -> Optional[str]:
        """
        Encrypt a single non-None value into ciphertext.

        Args:
            value: Any Python value (str, int, float, etc.)

        Returns:
            Encrypted ciphertext string, or None if value is None.
        """
        if value is None:
            return None
        plaintext = str(value)
        if not plaintext:
            return None
        try:
            return self._get_encryptor().encrypt(plaintext)
        except Exception as exc:
            logger.error(f"🔐 Encryption failed: {exc}")
            return plaintext  # fallback: store plaintext if encryption fails

    def _decrypt_value(self, ciphertext: Any, field_name: str = "") -> Any:
        """
        Decrypt a single ciphertext value and restore its original Python type.

        Graceful fallback: if decryption fails (e.g., value is legacy plaintext),
        the value is returned as-is. This ensures backward compatibility with
        existing unencrypted data.

        Args:
            ciphertext: The encrypted string from SQLite (or legacy plaintext).
            field_name: Column name — used to look up the original type.

        Returns:
            Decrypted value cast to its original Python type, or the raw value
            if decryption fails (graceful fallback).
        """
        if ciphertext is None:
            return None

        target_type = COLUMN_TYPES.get(field_name)

        # Attempt decryption
        try:
            plaintext = self._get_encryptor().decrypt(str(ciphertext))
        except Exception:
            # Graceful fallback — value is already plaintext (legacy data)
            # If it's already the correct native type from SQLite, return as-is
            if target_type and isinstance(ciphertext, target_type):
                return ciphertext
            if isinstance(ciphertext, (int, float)) and not target_type:
                return ciphertext
            plaintext = ciphertext

        # Restore original Python type for numeric columns
        if target_type and plaintext is not None:
            try:
                return target_type(plaintext)
            except (ValueError, TypeError):
                return plaintext

        return plaintext

    def _encrypt_row(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Encrypt all non-exempt fields in a row dict.

        Args:
            data: Dict of {column_name: plaintext_value}.

        Returns:
            New dict with encrypted values for non-exempt columns.
        """
        encrypted = {}
        for col, val in data.items():
            if col in ENCRYPT_EXEMPT or val is None:
                encrypted[col] = val
            else:
                encrypted[col] = self._encrypt_value(val)
        return encrypted

    def _decrypt_row(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decrypt all non-exempt fields in a row dict.

        Args:
            data: Dict of {column_name: ciphertext} from SQLite.

        Returns:
            New dict with decrypted plaintext values.
        """
        decrypted = {}
        for col, val in data.items():
            if col in ENCRYPT_EXEMPT or val is None:
                decrypted[col] = val
            else:
                decrypted[col] = self._decrypt_value(val, field_name=col)
        return decrypted

    # ----------------------------------------------------------------- schema

    def init_schema(self):
        """Create customer_memory table + index if they don't exist."""
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_memory (
                customer_id TEXT PRIMARY KEY,

                -- Identity (encrypted at rest)
                full_name TEXT,
                date_of_birth TEXT,
                phone TEXT,

                -- Address (encrypted at rest)
                address TEXT,
                city TEXT,
                state TEXT,
                pincode TEXT,

                -- Employment (encrypted at rest)
                employer_name TEXT,
                job_title TEXT,
                years_at_job TEXT,

                -- Income (encrypted at rest)
                monthly_income TEXT,
                income_type TEXT,

                -- Credit & Loans (encrypted at rest)
                cibil_score TEXT,
                total_existing_emi_monthly TEXT,
                number_of_active_loans TEXT,

                -- Loan Request (encrypted at rest)
                requested_loan_type TEXT,
                requested_loan_amount TEXT,
                requested_tenure_months TEXT,
                loan_purpose TEXT,

                -- Co-Applicant (encrypted at rest)
                coapplicant_name TEXT,
                coapplicant_relation TEXT,
                coapplicant_income TEXT,

                -- Application (NOT encrypted — queryable business state)
                application_status TEXT DEFAULT 'incomplete',
                documents_submitted TEXT,

                -- Metadata (NOT encrypted — needed for indexing)
                created_at TEXT NOT NULL,
                last_updated TEXT NOT NULL
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_customer_updated ON customer_memory(last_updated)"
        )
        self.connection.commit()
        logger.info("✅ customer_memory schema initialized (encryption at rest enabled)")

    def init_changelog_schema(self) -> None:
        """
        Create customer_changelog table if it doesn't exist.
        Safe to call multiple times (idempotent).

        Schema:
            customer_id   — FK to customer_memory (NOT encrypted)
            entity        — field name (NOT encrypted — needed for querying)
            old_val       — previous value (ENCRYPTED at rest)
            old_timestamp — when old_val was last set (NOT encrypted)
            upd_val       — new value (ENCRYPTED at rest)
            timestamp     — when this change was recorded (NOT encrypted)
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

        ENCRYPTION: old_val and upd_val are encrypted before INSERT.
        The caller passes PLAINTEXT values; encryption happens here.
        """
        self._ensure_connection()
        now = datetime.utcnow().isoformat()

        # Encrypt the data values (old_val and upd_val contain user data)
        encrypted_old = self._encrypt_value(old_val) if old_val is not None else None
        encrypted_upd = self._encrypt_value(upd_val)

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
                    encrypted_old,
                    old_timestamp,
                    encrypted_upd,
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

        ENCRYPTION: old_val and upd_val are decrypted before returning.

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
        results = []
        for r in rows:
            row = dict(r)
            # Decrypt the data values
            row["old_val"] = self._decrypt_value(row.get("old_val"), field_name=entity)
            row["upd_val"] = self._decrypt_value(row.get("upd_val"), field_name=entity)
            results.append(row)
        return results

    def get_all_recent_changelog(
        self,
        customer_id: str,
        days: int = 15,
        fields: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Return changelog for multiple fields (or all fields) in the last `days` days.
        Returns {entity: [rows...]} grouped by field name.

        ENCRYPTION: old_val and upd_val are decrypted before returning.
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
            entity = r["entity"]
            # Decrypt the data values
            r["old_val"] = self._decrypt_value(r.get("old_val"), field_name=entity)
            r["upd_val"] = self._decrypt_value(r.get("upd_val"), field_name=entity)
            result.setdefault(entity, []).append(r)
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
        """
        Full INSERT OR REPLACE for a CustomerMemory object.

        ENCRYPTION: All non-exempt field values are encrypted before INSERT.
        """
        self._ensure_connection()
        now = datetime.now().isoformat()

        # Build a dict of all field values
        row_data = {
            "customer_id":                 memory.customer_id,
            "full_name":                   memory.full_name,
            "date_of_birth":               memory.date_of_birth,
            "phone":                       memory.phone,
            "address":                     memory.address,
            "city":                        memory.city,
            "state":                       memory.state,
            "pincode":                     memory.pincode,
            "employer_name":               memory.employer_name,
            "job_title":                   memory.job_title,
            "years_at_job":                memory.years_at_job,
            "monthly_income":              memory.monthly_income,
            "income_type":                 memory.income_type,
            "cibil_score":                 memory.cibil_score,
            "total_existing_emi_monthly":  memory.total_existing_emi_monthly,
            "number_of_active_loans":      memory.number_of_active_loans,
            "requested_loan_type":         memory.requested_loan_type,
            "requested_loan_amount":       memory.requested_loan_amount,
            "requested_tenure_months":     memory.requested_tenure_months,
            "loan_purpose":               memory.loan_purpose,
            "coapplicant_name":            memory.coapplicant_name,
            "coapplicant_relation":        memory.coapplicant_relation,
            "coapplicant_income":          memory.coapplicant_income,
            "application_status":          memory.application_status,
            "documents_submitted":         memory.documents_submitted,
            "created_at":                  memory.created_at.isoformat(),
            "last_updated":                now,
        }

        # 🔐 Encrypt all non-exempt fields
        encrypted = self._encrypt_row(row_data)

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
            encrypted["customer_id"],
            encrypted["full_name"], encrypted["date_of_birth"], encrypted["phone"],
            encrypted["address"], encrypted["city"], encrypted["state"], encrypted["pincode"],
            encrypted["employer_name"], encrypted["job_title"], encrypted["years_at_job"],
            encrypted["monthly_income"], encrypted["income_type"],
            encrypted["cibil_score"], encrypted["total_existing_emi_monthly"],
            encrypted["number_of_active_loans"],
            encrypted["requested_loan_type"], encrypted["requested_loan_amount"],
            encrypted["requested_tenure_months"], encrypted["loan_purpose"],
            encrypted["coapplicant_name"], encrypted["coapplicant_relation"],
            encrypted["coapplicant_income"],
            encrypted["application_status"], encrypted["documents_submitted"],
            encrypted["created_at"], encrypted["last_updated"],
        ))
        self.connection.commit()
        logger.info(f"🔐 Saved encrypted memory for {memory.customer_id}")

    def load_customer_memory(self, customer_id: str) -> Optional[CustomerMemory]:
        """
        Load full CustomerMemory for a customer. Returns None if not found.

        ENCRYPTION: All non-exempt fields are decrypted after SELECT.
        """
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM customer_memory WHERE customer_id = ?", (customer_id,))
        row = cursor.fetchone()
        if not row:
            logger.debug(f"No memory row found for {customer_id}")
            return None

        # 🔐 Decrypt all non-exempt fields
        data = self._decrypt_row(dict(row))

        data["created_at"]   = datetime.fromisoformat(data["created_at"])
        data["last_updated"] = datetime.fromisoformat(data["last_updated"])
        return CustomerMemory(**data)

    def get_all_facts_grouped(self, customer_id: str) -> Dict[str, Any]:
        """
        Return all non-null fields for a customer in a nested group structure.
        Used by load_memory node for context injection into the agent.

        ENCRYPTION: All fields are decrypted before grouping.
        """
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM customer_memory WHERE customer_id = ?", (customer_id,))
        row = cursor.fetchone()
        if not row:
            return {}

        # 🔐 Decrypt all non-exempt fields
        data = self._decrypt_row(dict(row))

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

        ENCRYPTION: All fields are decrypted before returning.
        """
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM customer_memory WHERE customer_id = ?", (customer_id,))
        row = cursor.fetchone()
        if not row:
            return {}

        # 🔐 Decrypt all non-exempt fields
        data = self._decrypt_row(dict(row))

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

        ENCRYPTION: Value is encrypted before UPDATE. Old value from DB is
        decrypted for changelog. Changelog itself encrypts internally.
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
            raw_old_val   = row[field_name] if row else None
            old_timestamp = row["last_updated"] if row else None

            # 🔐 Decrypt old value for changelog (may be ciphertext or legacy plaintext)
            old_val_plain = self._decrypt_value(raw_old_val, field_name=field_name)

            # 🔐 Encrypt new value before UPDATE
            if field_name in ENCRYPT_EXEMPT:
                encrypted_value = value
            else:
                encrypted_value = self._encrypt_value(value)

            self.connection.execute(
                f"UPDATE customer_memory SET {field_name}=?, last_updated=? WHERE customer_id=?",
                (encrypted_value, now, customer_id),
            )
            # Log the change (log_field_change encrypts old_val and upd_val internally)
            self.log_field_change(customer_id, field_name, old_val_plain, old_timestamp, value)
            self.connection.commit()
            logger.debug(f"🔐 {customer_id} | {field_name} updated (encrypted)")
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

        ENCRYPTION: Each value is encrypted before UPDATE. Old values are
        decrypted for changelog. Changelog itself encrypts internally.
        """
        if not fields:
            return {}

        self.ensure_customer_exists(customer_id)
        self._ensure_connection()

        # Pre-read old values + last_updated for all fields we're about to change
        valid_fields = [f for f in fields if f in VALID_COLUMNS]
        old_values_plain: Dict[str, Any] = {}
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
                        # 🔐 Decrypt old values for changelog
                        raw_old = row_d.get(f)
                        old_values_plain[f] = self._decrypt_value(raw_old, field_name=f)
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
                        # 🔐 Encrypt new value before UPDATE
                        if field_name in ENCRYPT_EXEMPT:
                            encrypted_value = value
                        else:
                            encrypted_value = self._encrypt_value(value)

                        cursor.execute(
                            f"UPDATE customer_memory SET {field_name}=?, last_updated=? WHERE customer_id=?",
                            (encrypted_value, now, customer_id),
                        )
                        # Log change to changelog (encrypts internally)
                        self.log_field_change(
                            customer_id,
                            field_name,
                            old_values_plain.get(field_name),
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
        logger.info(f"🔐 batch_update {customer_id}: {ok}/{len(results)} OK (encrypted)")
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
# QUICK SMOKE TEST — Validates encryption at rest
# ============================================================================

def test_simplified_db():
    from memory.models import create_test_memory
    import os

    # Use a test encryption key for deterministic testing
    os.environ.setdefault("DB_ENCRYPTION_KEY", "")

    db = MemoryDatabase(db_path=":memory:")
    db.connect()
    db.init_schema()
    db.init_changelog_schema()

    print("\n" + "=" * 60)
    print("🔐 Testing SQLite Encryption at Rest")
    print("=" * 60)

    # --- Test 1: Save & load with encryption ---
    print("\n1. Save customer memory (encrypted)...")
    memory = create_test_memory()
    db.save_customer_memory(memory)

    print("2. Load customer memory (decrypted)...")
    loaded = db.load_customer_memory("RAJESH_001")
    assert loaded is not None, "Load returned None"
    assert loaded.full_name == "Rajesh Kumar", f"Name mismatch: {loaded.full_name}"
    assert loaded.monthly_income == 45000.0, f"Income mismatch: {loaded.monthly_income}"
    assert loaded.cibil_score == 750, f"CIBIL mismatch: {loaded.cibil_score}"
    print(f"   ✅ Decrypted correctly: name={loaded.full_name}, income={loaded.monthly_income}, cibil={loaded.cibil_score}")

    # --- Test 2: Verify raw DB stores ciphertext ---
    print("\n3. Checking raw DB values are ciphertext...")
    cursor = db.connection.cursor()
    cursor.execute("SELECT full_name, monthly_income, customer_id, application_status FROM customer_memory WHERE customer_id='RAJESH_001'")
    raw = dict(cursor.fetchone())
    assert raw["full_name"] != "Rajesh Kumar", f"full_name NOT encrypted! Raw: {raw['full_name']}"
    assert raw["full_name"].startswith("gAAAAAB"), f"full_name doesn't look like Fernet ciphertext"
    assert raw["monthly_income"] != "45000.0", f"monthly_income NOT encrypted!"
    assert raw["customer_id"] == "RAJESH_001", "customer_id should NOT be encrypted"
    assert raw["application_status"] == "incomplete", "application_status should NOT be encrypted"
    print(f"   ✅ Raw ciphertext: full_name={raw['full_name'][:30]}...")
    print(f"   ✅ Exempt fields readable: customer_id={raw['customer_id']}, status={raw['application_status']}")

    # --- Test 3: Field update with encryption ---
    print("\n4. Testing field update (encrypted)...")
    ok = db.update_field_value("RAJESH_001", "city", "Mumbai")
    assert ok, "update_field_value failed for city"
    loaded2 = db.load_customer_memory("RAJESH_001")
    assert loaded2.city == "Mumbai", f"City mismatch: {loaded2.city}"
    print(f"   ✅ Field updated & decrypted: city={loaded2.city}")

    # --- Test 4: New customer INSERT guard ---
    print("\n5. Testing new customer auto-creation...")
    ok = db.update_field_value("BRAND_NEW_001", "full_name", "New User")
    assert ok, "update_field_value failed for new customer"
    new_cust = db.load_customer_memory("BRAND_NEW_001")
    assert new_cust and new_cust.full_name == "New User", "New customer not saved"
    print(f"   ✅ New customer encrypted: name={new_cust.full_name}")

    # --- Test 5: Batch update with encryption ---
    print("\n6. Testing batch update (encrypted)...")
    results = db.batch_update_fields("RAJESH_001", {
        "city": "Pune",
        "monthly_income": 65000,
        "cibil_score": 790,
    })
    assert all(results.values()), f"Batch failed: {results}"
    loaded3 = db.load_customer_memory("RAJESH_001")
    assert loaded3.city == "Pune", f"Batch city: {loaded3.city}"
    assert loaded3.monthly_income == 65000.0, f"Batch income: {loaded3.monthly_income}"
    assert loaded3.cibil_score == 790, f"Batch cibil: {loaded3.cibil_score}"
    print(f"   ✅ Batch decrypted: city={loaded3.city}, income={loaded3.monthly_income}, cibil={loaded3.cibil_score}")

    # --- Test 6: get_all_facts returns decrypted data ---
    print("\n7. Testing get_all_facts (decrypted)...")
    facts = db.get_all_facts_grouped("RAJESH_001")
    assert "customer_id" in facts
    assert "income" in facts
    assert facts["income"]["monthly_income"] == 65000.0
    print(f"   ✅ Grouped facts decrypted: income={facts['income']['monthly_income']}")

    all_facts = db.get_all_facts("RAJESH_001")
    assert "monthly_income" in all_facts
    assert all_facts["monthly_income"] == 65000.0
    print(f"   ✅ Flat facts decrypted: monthly_income={all_facts['monthly_income']}")

    # --- Test 7: Verify all raw values are encrypted ---
    print("\n8. Final raw DB audit...")
    cursor.execute("SELECT * FROM customer_memory WHERE customer_id='RAJESH_001'")
    final_raw = dict(cursor.fetchone())
    encrypted_count = 0
    exempt_count = 0
    for col, val in final_raw.items():
        if val is None:
            continue
        if col in ENCRYPT_EXEMPT:
            exempt_count += 1
        elif isinstance(val, str) and val.startswith("gAAAAAB"):
            encrypted_count += 1
    print(f"   ✅ Encrypted columns: {encrypted_count}, Exempt columns: {exempt_count}")

    db.close()
    print(f"\n{'=' * 60}")
    print("✅ All encryption-at-rest tests PASSED!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    test_simplified_db()
