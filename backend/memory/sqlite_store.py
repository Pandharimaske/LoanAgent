"""
SQLite database operations for customer memory.
2-table approach: non_pii (plaintext) + pii (encrypted).
Stores factual/structured data. Session summaries go to ChromaDB.
"""

import sys
import sqlite3
import json
from pathlib import Path
from typing import Optional, Tuple, List
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import SQLITE_PATH
from memory.models import (
    CustomerMemoryNonPII,
    CustomerMemoryPII,
    SessionLog,
    FieldChangeLog,
    FixedEntity,
    LoanRequest,
    EmploymentHistory,
    DocumentSubmission,
    CoApplicant,
    Guarantor,
    ApplicationStatus,
    create_test_memory,
)
from memory.encryption import get_encryption_manager


class MemoryDatabase:
    """SQLite database manager for customer memory."""

    # Fields in CustomerMemoryPII that need encryption
    PII_ENCRYPTED_FIELDS = [
        "full_name",
        "date_of_birth",
        "gender",
        "marital_status",
        "primary_phone",
        "current_address",
        "city",
        "state",
        "pincode",
        "employer_name",
        "years_at_current_job",
        "co_applicants",
        "guarantors",
    ]

    def __init__(self, db_path: str = SQLITE_PATH):
        self.db_path = db_path
        self.connection = None
        self.encryption = get_encryption_manager()

    def connect(self) -> sqlite3.Connection:
        """Connect to database and enable foreign keys."""
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        return self.connection

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()
            self.connection = None

    def _ensure_connection(self):
        """Ensure database connection exists."""
        if not self.connection:
            self.connect()

    # ========================================================================
    # SCHEMA
    # ========================================================================

    def init_schema(self):
        """Create tables if they don't exist."""
        self._ensure_connection()
        cursor = self.connection.cursor()

        # Non-PII table (plaintext storage)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_memory_nonpii (
                customer_id TEXT PRIMARY KEY,
                monthly_income_json TEXT,
                income_type_json TEXT,
                total_work_experience_years_json TEXT,
                employment_history_json TEXT,
                cibil_score_json TEXT,
                cibil_last_checked TEXT,
                total_existing_emi_monthly_json TEXT,
                number_of_active_loans_json TEXT,
                loan_request_json TEXT,
                documents_submitted_json TEXT,
                application_status TEXT DEFAULT 'incomplete',
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                last_updated TEXT NOT NULL
            )
        """)

        # PII table (encrypted storage)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customer_memory_pii (
                customer_id TEXT PRIMARY KEY,
                full_name_encrypted TEXT,
                date_of_birth_encrypted TEXT,
                gender_encrypted TEXT,
                marital_status_encrypted TEXT,
                pan_hash TEXT UNIQUE,
                aadhaar_hash TEXT UNIQUE,
                primary_phone_encrypted TEXT,
                current_address_encrypted TEXT,
                city_encrypted TEXT,
                state_encrypted TEXT,
                pincode_encrypted TEXT,
                employer_name_encrypted TEXT,
                years_at_current_job_encrypted TEXT,
                co_applicants_encrypted TEXT,
                guarantors_encrypted TEXT,
                created_at TEXT NOT NULL,
                last_updated TEXT NOT NULL,
                FOREIGN KEY (customer_id) REFERENCES customer_memory_nonpii(customer_id)
            )
        """)

        # Session log table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_log (
                session_id TEXT PRIMARY KEY,
                customer_id TEXT NOT NULL,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                agent_id TEXT,
                turns_json TEXT DEFAULT '[]',
                summary TEXT,
                FOREIGN KEY (customer_id) REFERENCES customer_memory_nonpii(customer_id)
            )
        """)

        # Field change log (audit trail)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS field_change_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                changed_at TEXT NOT NULL,
                session_id TEXT NOT NULL,
                conflict_detected INTEGER DEFAULT 0,
                user_confirmed INTEGER DEFAULT 0,
                confirmation_timestamp TEXT,
                FOREIGN KEY (customer_id) REFERENCES customer_memory_nonpii(customer_id),
                FOREIGN KEY (session_id) REFERENCES session_log(session_id)
            )
        """)

        # Indexes
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_customer ON session_log(customer_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_started ON session_log(started_at)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_change_customer ON field_change_log(customer_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_change_session ON field_change_log(session_id)"
        )

        self.connection.commit()

    # ========================================================================
    # HELPERS — Serialize/Deserialize
    # ========================================================================

    @staticmethod
    def _entity_to_json(entity: Optional[FixedEntity]) -> Optional[str]:
        """Serialize FixedEntity to JSON string."""
        if entity is None:
            return None
        return entity.model_dump_json()

    @staticmethod
    def _entity_from_json(data: Optional[str]) -> Optional[FixedEntity]:
        """Deserialize FixedEntity from JSON string."""
        if not data:
            return None
        return FixedEntity.model_validate_json(data)

    # ========================================================================
    # CUSTOMER MEMORY — SAVE
    # ========================================================================

    def save_customer_memory(
        self, nonpii: CustomerMemoryNonPII, pii: CustomerMemoryPII
    ) -> bool:
        """
        Save customer memory (both non-PII and PII).
        Uses INSERT OR REPLACE (upsert).
        """
        self._ensure_connection()

        try:
            cursor = self.connection.cursor()

            # ---- Save Non-PII ----
            cursor.execute(
                """
                INSERT OR REPLACE INTO customer_memory_nonpii (
                    customer_id, monthly_income_json, income_type_json,
                    total_work_experience_years_json, employment_history_json,
                    cibil_score_json, cibil_last_checked,
                    total_existing_emi_monthly_json, number_of_active_loans_json,
                    loan_request_json, documents_submitted_json,
                    application_status, is_active, created_at, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    nonpii.customer_id,
                    self._entity_to_json(nonpii.monthly_income),
                    self._entity_to_json(nonpii.income_type),
                    self._entity_to_json(nonpii.total_work_experience_years),
                    json.dumps(
                        [h.model_dump() for h in nonpii.employment_history],
                        default=str,
                    ),
                    self._entity_to_json(nonpii.cibil_score),
                    nonpii.cibil_last_checked.isoformat()
                    if nonpii.cibil_last_checked
                    else None,
                    self._entity_to_json(nonpii.total_existing_emi_monthly),
                    self._entity_to_json(nonpii.number_of_active_loans),
                    nonpii.loan_request.model_dump_json()
                    if nonpii.loan_request
                    else None,
                    json.dumps(
                        [d.model_dump() for d in nonpii.documents_submitted],
                        default=str,
                    ),
                    nonpii.application_status.value
                    if isinstance(nonpii.application_status, ApplicationStatus)
                    else nonpii.application_status,
                    1 if nonpii.is_active else 0,
                    nonpii.created_at.isoformat(),
                    datetime.now().isoformat(),
                ),
            )

            # ---- Save PII (with encryption) ----
            pii_data = {
                "full_name": self._entity_to_json(pii.full_name),
                "date_of_birth": self._entity_to_json(pii.date_of_birth),
                "gender": self._entity_to_json(pii.gender),
                "marital_status": self._entity_to_json(pii.marital_status),
                "primary_phone": self._entity_to_json(pii.primary_phone),
                "current_address": self._entity_to_json(pii.current_address),
                "city": self._entity_to_json(pii.city),
                "state": self._entity_to_json(pii.state),
                "pincode": self._entity_to_json(pii.pincode),
                "employer_name": self._entity_to_json(pii.employer_name),
                "years_at_current_job": self._entity_to_json(pii.years_at_current_job),
                "co_applicants": json.dumps(
                    [c.model_dump() for c in pii.co_applicants], default=str
                ),
                "guarantors": json.dumps(
                    [g.model_dump() for g in pii.guarantors], default=str
                ),
            }

            # Encrypt PII fields
            for field in self.PII_ENCRYPTED_FIELDS:
                if field in pii_data and pii_data[field]:
                    try:
                        pii_data[field] = self.encryption.encrypt(pii_data[field])
                    except Exception as e:
                        print(f"[WARN] Failed to encrypt {field}: {e}")

            cursor.execute(
                """
                INSERT OR REPLACE INTO customer_memory_pii (
                    customer_id, full_name_encrypted, date_of_birth_encrypted,
                    gender_encrypted, marital_status_encrypted,
                    pan_hash, aadhaar_hash,
                    primary_phone_encrypted, current_address_encrypted,
                    city_encrypted, state_encrypted, pincode_encrypted,
                    employer_name_encrypted, years_at_current_job_encrypted,
                    co_applicants_encrypted, guarantors_encrypted,
                    created_at, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pii.customer_id,
                    pii_data["full_name"],
                    pii_data["date_of_birth"],
                    pii_data["gender"],
                    pii_data["marital_status"],
                    pii.pan_hash,
                    pii.aadhaar_hash,
                    pii_data["primary_phone"],
                    pii_data["current_address"],
                    pii_data["city"],
                    pii_data["state"],
                    pii_data["pincode"],
                    pii_data["employer_name"],
                    pii_data["years_at_current_job"],
                    pii_data["co_applicants"],
                    pii_data["guarantors"],
                    pii.created_at.isoformat(),
                    datetime.now().isoformat(),
                ),
            )

            self.connection.commit()
            return True

        except Exception as e:
            print(f"[ERROR] Failed to save customer memory: {e}")
            self.connection.rollback()
            return False

    # ========================================================================
    # CUSTOMER MEMORY — LOAD (COMPLETE)
    # ========================================================================

    def load_customer_memory(
        self, customer_id: str
    ) -> Tuple[Optional[CustomerMemoryNonPII], Optional[CustomerMemoryPII]]:
        """
        Load customer memory (both non-PII and PII) with full deserialization.

        Returns:
            Tuple of (NonPII, PII) or (None, None) if not found.
        """
        self._ensure_connection()

        try:
            cursor = self.connection.cursor()

            # ---- Load Non-PII ----
            cursor.execute(
                "SELECT * FROM customer_memory_nonpii WHERE customer_id = ?",
                (customer_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None, None

            r = dict(row)

            # Deserialize all FixedEntity JSON fields
            monthly_income = self._entity_from_json(r["monthly_income_json"])
            income_type = self._entity_from_json(r["income_type_json"])
            total_work_exp = self._entity_from_json(
                r["total_work_experience_years_json"]
            )
            cibil_score = self._entity_from_json(r["cibil_score_json"])
            total_emi = self._entity_from_json(r["total_existing_emi_monthly_json"])
            num_loans = self._entity_from_json(r["number_of_active_loans_json"])

            # Deserialize LoanRequest
            loan_request = None
            if r["loan_request_json"]:
                loan_request = LoanRequest.model_validate_json(r["loan_request_json"])

            # Deserialize employment history list
            employment_history = []
            if r["employment_history_json"]:
                raw_list = json.loads(r["employment_history_json"])
                employment_history = [
                    EmploymentHistory.model_validate(item) for item in raw_list
                ]

            # Deserialize documents submitted list
            documents_submitted = []
            if r["documents_submitted_json"]:
                raw_docs = json.loads(r["documents_submitted_json"])
                documents_submitted = [
                    DocumentSubmission.model_validate(item) for item in raw_docs
                ]

            # Parse application status
            app_status = ApplicationStatus.INCOMPLETE
            if r["application_status"]:
                try:
                    app_status = ApplicationStatus(r["application_status"])
                except ValueError:
                    pass

            nonpii = CustomerMemoryNonPII(
                customer_id=r["customer_id"],
                monthly_income=monthly_income,
                income_type=income_type,
                total_work_experience_years=total_work_exp,
                employment_history=employment_history,
                cibil_score=cibil_score,
                cibil_last_checked=datetime.fromisoformat(r["cibil_last_checked"])
                if r["cibil_last_checked"]
                else None,
                total_existing_emi_monthly=total_emi,
                number_of_active_loans=num_loans,
                loan_request=loan_request,
                documents_submitted=documents_submitted,
                application_status=app_status,
                is_active=bool(r["is_active"]),
                created_at=datetime.fromisoformat(r["created_at"]),
                last_updated=datetime.fromisoformat(r["last_updated"]),
            )

            # ---- Load PII ----
            cursor.execute(
                "SELECT * FROM customer_memory_pii WHERE customer_id = ?",
                (customer_id,),
            )
            pii_row = cursor.fetchone()

            if not pii_row:
                return nonpii, None

            p = dict(pii_row)

            # Decrypt PII fields
            for field in self.PII_ENCRYPTED_FIELDS:
                encrypted_col = f"{field}_encrypted"
                if encrypted_col in p and p[encrypted_col]:
                    try:
                        p[field] = self.encryption.decrypt(p[encrypted_col])
                    except Exception as e:
                        print(f"[WARN] Failed to decrypt {field}: {e}")
                        p[field] = None
                else:
                    p[field] = None

            # Deserialize PII FixedEntity fields
            full_name = self._entity_from_json(p.get("full_name"))
            dob = self._entity_from_json(p.get("date_of_birth"))
            gender = self._entity_from_json(p.get("gender"))
            marital = self._entity_from_json(p.get("marital_status"))
            phone = self._entity_from_json(p.get("primary_phone"))
            address = self._entity_from_json(p.get("current_address"))
            city = self._entity_from_json(p.get("city"))
            state = self._entity_from_json(p.get("state"))
            pincode = self._entity_from_json(p.get("pincode"))
            emp_name = self._entity_from_json(p.get("employer_name"))
            years_job = self._entity_from_json(p.get("years_at_current_job"))

            # Deserialize co_applicants list
            co_applicants = []
            if p.get("co_applicants"):
                try:
                    raw_co = json.loads(p["co_applicants"])
                    co_applicants = [
                        CoApplicant.model_validate(item) for item in raw_co
                    ]
                except (json.JSONDecodeError, Exception):
                    pass

            # Deserialize guarantors list
            guarantors = []
            if p.get("guarantors"):
                try:
                    raw_g = json.loads(p["guarantors"])
                    guarantors = [Guarantor.model_validate(item) for item in raw_g]
                except (json.JSONDecodeError, Exception):
                    pass

            pii = CustomerMemoryPII(
                customer_id=p["customer_id"],
                full_name=full_name,
                date_of_birth=dob,
                gender=gender,
                marital_status=marital,
                pan_hash=p.get("pan_hash"),
                aadhaar_hash=p.get("aadhaar_hash"),
                primary_phone=phone,
                current_address=address,
                city=city,
                state=state,
                pincode=pincode,
                employer_name=emp_name,
                years_at_current_job=years_job,
                co_applicants=co_applicants,
                guarantors=guarantors,
                created_at=datetime.fromisoformat(p["created_at"]),
                last_updated=datetime.fromisoformat(p["last_updated"]),
            )

            return nonpii, pii

        except Exception as e:
            print(f"[ERROR] Failed to load customer memory: {e}")
            import traceback
            traceback.print_exc()
            return None, None

    # ========================================================================
    # CUSTOMER — UTILITIES
    # ========================================================================

    def customer_exists(self, customer_id: str) -> bool:
        """Check if a customer exists in the database."""
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT 1 FROM customer_memory_nonpii WHERE customer_id = ?",
            (customer_id,),
        )
        return cursor.fetchone() is not None

    def list_customers(self) -> List[str]:
        """List all customer IDs."""
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("SELECT customer_id FROM customer_memory_nonpii ORDER BY customer_id")
        return [row["customer_id"] for row in cursor.fetchall()]

    def delete_customer(self, customer_id: str) -> bool:
        """Delete a customer and all related data. Use with caution."""
        self._ensure_connection()
        try:
            cursor = self.connection.cursor()
            cursor.execute("DELETE FROM field_change_log WHERE customer_id = ?", (customer_id,))
            cursor.execute("DELETE FROM session_log WHERE customer_id = ?", (customer_id,))
            cursor.execute("DELETE FROM customer_memory_pii WHERE customer_id = ?", (customer_id,))
            cursor.execute("DELETE FROM customer_memory_nonpii WHERE customer_id = ?", (customer_id,))
            self.connection.commit()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to delete customer: {e}")
            self.connection.rollback()
            return False

    # ========================================================================
    # SESSION LOG — CRUD
    # ========================================================================

    def save_session(self, session: SessionLog) -> bool:
        """Save or update a session log."""
        self._ensure_connection()
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO session_log (
                    session_id, customer_id, started_at, ended_at,
                    agent_id, turns_json, summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session.session_id,
                    session.customer_id,
                    session.started_at.isoformat(),
                    session.ended_at.isoformat() if session.ended_at else None,
                    session.agent_id,
                    json.dumps(session.turns, default=str),
                    session.summary,
                ),
            )
            self.connection.commit()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to save session: {e}")
            self.connection.rollback()
            return False

    def load_session(self, session_id: str) -> Optional[SessionLog]:
        """Load a session by ID."""
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute("SELECT * FROM session_log WHERE session_id = ?", (session_id,))
        row = cursor.fetchone()
        if not row:
            return None

        r = dict(row)
        return SessionLog(
            session_id=r["session_id"],
            customer_id=r["customer_id"],
            started_at=datetime.fromisoformat(r["started_at"]),
            ended_at=datetime.fromisoformat(r["ended_at"]) if r["ended_at"] else None,
            agent_id=r.get("agent_id"),
            turns=json.loads(r["turns_json"]) if r["turns_json"] else [],
            summary=r.get("summary"),
        )

    def get_customer_sessions(
        self, customer_id: str, limit: int = 50
    ) -> List[SessionLog]:
        """Get all sessions for a customer, ordered by start time."""
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute(
            "SELECT * FROM session_log WHERE customer_id = ? ORDER BY started_at DESC LIMIT ?",
            (customer_id, limit),
        )
        sessions = []
        for row in cursor.fetchall():
            r = dict(row)
            sessions.append(
                SessionLog(
                    session_id=r["session_id"],
                    customer_id=r["customer_id"],
                    started_at=datetime.fromisoformat(r["started_at"]),
                    ended_at=datetime.fromisoformat(r["ended_at"])
                    if r["ended_at"]
                    else None,
                    agent_id=r.get("agent_id"),
                    turns=json.loads(r["turns_json"]) if r["turns_json"] else [],
                    summary=r.get("summary"),
                )
            )
        return sessions

    def end_session(self, session_id: str, summary: Optional[str] = None) -> bool:
        """Mark a session as ended, optionally with a summary."""
        self._ensure_connection()
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE session_log SET ended_at = ?, summary = ? WHERE session_id = ?",
                (datetime.now().isoformat(), summary, session_id),
            )
            self.connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"[ERROR] Failed to end session: {e}")
            return False

    def add_turn_to_session(
        self, session_id: str, role: str, content: str
    ) -> bool:
        """Append a turn to an existing session's turns list."""
        self._ensure_connection()
        try:
            session = self.load_session(session_id)
            if not session:
                return False

            session.turns.append(
                {
                    "role": role,
                    "content": content,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            return self.save_session(session)
        except Exception as e:
            print(f"[ERROR] Failed to add turn: {e}")
            return False

    # ========================================================================
    # FIELD CHANGE LOG — Audit Trail
    # ========================================================================

    def log_field_change(
        self,
        customer_id: str,
        field_name: str,
        session_id: str,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        conflict_detected: bool = False,
    ) -> bool:
        """Log a field change for audit trail."""
        self._ensure_connection()
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                INSERT INTO field_change_log (
                    customer_id, field_name, old_value, new_value,
                    changed_at, session_id, conflict_detected
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    customer_id,
                    field_name,
                    old_value,
                    new_value,
                    datetime.now().isoformat(),
                    session_id,
                    1 if conflict_detected else 0,
                ),
            )
            self.connection.commit()
            return True
        except Exception as e:
            print(f"[ERROR] Failed to log field change: {e}")
            return False

    def confirm_field_change(self, change_id: int) -> bool:
        """Mark a field change as user-confirmed."""
        self._ensure_connection()
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                """
                UPDATE field_change_log 
                SET user_confirmed = 1, confirmation_timestamp = ?
                WHERE id = ?
                """,
                (datetime.now().isoformat(), change_id),
            )
            self.connection.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"[ERROR] Failed to confirm field change: {e}")
            return False

    def get_field_changes(
        self,
        customer_id: str,
        field_name: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[FieldChangeLog]:
        """Get field change history with optional filters."""
        self._ensure_connection()
        cursor = self.connection.cursor()

        query = "SELECT * FROM field_change_log WHERE customer_id = ?"
        params = [customer_id]

        if field_name:
            query += " AND field_name = ?"
            params.append(field_name)
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)

        query += " ORDER BY changed_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)

        changes = []
        for row in cursor.fetchall():
            r = dict(row)
            changes.append(
                FieldChangeLog(
                    id=r["id"],
                    customer_id=r["customer_id"],
                    field_name=r["field_name"],
                    old_value=r.get("old_value"),
                    new_value=r.get("new_value"),
                    changed_at=datetime.fromisoformat(r["changed_at"]),
                    session_id=r["session_id"],
                    conflict_detected=bool(r["conflict_detected"]),
                    user_confirmed=bool(r["user_confirmed"]),
                    confirmation_timestamp=datetime.fromisoformat(
                        r["confirmation_timestamp"]
                    )
                    if r.get("confirmation_timestamp")
                    else None,
                )
            )
        return changes

    def get_unconfirmed_conflicts(self, customer_id: str) -> List[FieldChangeLog]:
        """Get all unresolved conflicts for a customer."""
        self._ensure_connection()
        cursor = self.connection.cursor()
        cursor.execute(
            """
            SELECT * FROM field_change_log 
            WHERE customer_id = ? AND conflict_detected = 1 AND user_confirmed = 0
            ORDER BY changed_at DESC
            """,
            (customer_id,),
        )
        return [
            FieldChangeLog(
                id=dict(row)["id"],
                customer_id=dict(row)["customer_id"],
                field_name=dict(row)["field_name"],
                old_value=dict(row).get("old_value"),
                new_value=dict(row).get("new_value"),
                changed_at=datetime.fromisoformat(dict(row)["changed_at"]),
                session_id=dict(row)["session_id"],
                conflict_detected=True,
                user_confirmed=False,
            )
            for row in cursor.fetchall()
        ]

    # ========================================================================
    # CONTEXT MANAGERS
    # ========================================================================

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ============================================================================
# TEST
# ============================================================================


def test_database():
    """Test full database operations."""
    print("=" * 70)
    print("Testing Memory Database")
    print("=" * 70)

    db = MemoryDatabase(db_path=":memory:")

    # 1. Init
    print("\n1. Initializing schema...")
    db.connect()
    db.init_schema()
    print("   [OK] Schema created")

    # 2. Create test data
    print("\n2. Creating test data (Rajesh scenario)...")
    nonpii, pii = create_test_memory()
    print(f"   [OK] Test data created for {nonpii.customer_id}")

    # 3. Save
    print("\n3. Saving to database...")
    success = db.save_customer_memory(nonpii, pii)
    assert success, "Save failed!"
    print("   [OK] Saved successfully")

    # 4. Load and verify ALL fields
    print("\n4. Loading from database...")
    loaded_nonpii, loaded_pii = db.load_customer_memory(nonpii.customer_id)

    assert loaded_nonpii is not None, "NonPII load failed!"
    assert loaded_pii is not None, "PII load failed!"
    print("   [OK] Loaded successfully")

    # Verify Non-PII fields
    assert loaded_nonpii.customer_id == "RAJESH_001"
    assert loaded_nonpii.monthly_income is not None
    assert loaded_nonpii.monthly_income.current.value == 45000
    print(f"   [OK] monthly_income: {loaded_nonpii.monthly_income.current.value}")

    assert loaded_nonpii.income_type is not None
    assert loaded_nonpii.income_type.current.value == "salaried"
    print(f"   [OK] income_type: {loaded_nonpii.income_type.current.value}")

    assert loaded_nonpii.cibil_score is not None
    assert loaded_nonpii.cibil_score.current.value == 750
    print(f"   [OK] cibil_score: {loaded_nonpii.cibil_score.current.value}")

    assert loaded_nonpii.total_existing_emi_monthly is not None
    assert loaded_nonpii.total_existing_emi_monthly.current.value == 15000
    print(f"   [OK] total_emi: {loaded_nonpii.total_existing_emi_monthly.current.value}")

    assert loaded_nonpii.loan_request is not None
    assert loaded_nonpii.loan_request.loan_amount.current.value == 2500000
    print(f"   [OK] loan_amount: {loaded_nonpii.loan_request.loan_amount.current.value}")

    # Verify PII fields
    assert loaded_pii.full_name is not None
    assert loaded_pii.full_name.current.value == "Rajesh Kumar"
    print(f"   [OK] full_name: {loaded_pii.full_name.current.value} (encrypted+decrypted)")

    assert loaded_pii.primary_phone is not None
    assert loaded_pii.primary_phone.current.value == "9876543210"
    print(f"   [OK] phone: {loaded_pii.primary_phone.current.value} (encrypted+decrypted)")

    assert loaded_pii.city is not None
    assert loaded_pii.city.current.value == "Bangalore"
    print(f"   [OK] city: {loaded_pii.city.current.value} (encrypted+decrypted)")

    assert len(loaded_pii.co_applicants) == 1
    assert loaded_pii.co_applicants[0].name.current.value == "Sunita Kumar"
    print(f"   [OK] co_applicant: {loaded_pii.co_applicants[0].name.current.value} (encrypted+decrypted)")

    # 5. Session CRUD
    print("\n5. Testing session CRUD...")
    session = SessionLog(
        session_id="S1",
        customer_id="RAJESH_001",
        started_at=datetime.now(),
        agent_id="AGENT_A",
        turns=[
            {"role": "user", "content": "I need a home loan", "timestamp": datetime.now().isoformat()},
            {"role": "assistant", "content": "Sure, what is your income?", "timestamp": datetime.now().isoformat()},
        ],
    )
    assert db.save_session(session), "Session save failed!"
    print("   [OK] Session saved")

    loaded_session = db.load_session("S1")
    assert loaded_session is not None
    assert loaded_session.customer_id == "RAJESH_001"
    assert len(loaded_session.turns) == 2
    print(f"   [OK] Session loaded: {len(loaded_session.turns)} turns")

    db.add_turn_to_session("S1", "user", "My income is 45000")
    loaded_session = db.load_session("S1")
    assert len(loaded_session.turns) == 3
    print(f"   [OK] Turn added: {len(loaded_session.turns)} turns")

    db.end_session("S1", summary="Rajesh needs home loan. Income 45k.")
    loaded_session = db.load_session("S1")
    assert loaded_session.ended_at is not None
    assert loaded_session.summary is not None
    print(f"   [OK] Session ended with summary")

    sessions = db.get_customer_sessions("RAJESH_001")
    assert len(sessions) == 1
    print(f"   [OK] Customer sessions: {len(sessions)}")

    # 6. Field change log — create S3 session first (FK requirement)
    print("\n6. Testing field change log...")
    session_s3 = SessionLog(
        session_id="S3",
        customer_id="RAJESH_001",
        started_at=datetime.now(),
        agent_id="AGENT_B",
    )
    db.save_session(session_s3)

    db.log_field_change(
        customer_id="RAJESH_001",
        field_name="monthly_income",
        session_id="S1",
        old_value=None,
        new_value="45000",
    )
    db.log_field_change(
        customer_id="RAJESH_001",
        field_name="monthly_income",
        session_id="S3",
        old_value="45000",
        new_value="60000",
        conflict_detected=True,
    )
    print("   [OK] Changes logged")

    changes = db.get_field_changes("RAJESH_001", field_name="monthly_income")
    assert len(changes) == 2
    print(f"   [OK] Field changes: {len(changes)}")

    conflicts = db.get_unconfirmed_conflicts("RAJESH_001")
    assert len(conflicts) == 1
    print(f"   [OK] Unconfirmed conflicts: {len(conflicts)}")

    db.confirm_field_change(conflicts[0].id)
    conflicts = db.get_unconfirmed_conflicts("RAJESH_001")
    assert len(conflicts) == 0
    print(f"   [OK] Conflict resolved: {len(conflicts)} remaining")

    # 7. Utilities
    print("\n7. Testing utilities...")
    assert db.customer_exists("RAJESH_001")
    print("   [OK] customer_exists: True")

    customers = db.list_customers()
    assert "RAJESH_001" in customers
    print(f"   [OK] list_customers: {customers}")

    db.close()
    print("\n[ALL TESTS PASSED]")
    print("=" * 70)


if __name__ == "__main__":
    test_database()
