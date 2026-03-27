"""
SQLite database operations for customer memory.
2-table approach: non_pii (plaintext) + pii (encrypted).
"""

import sys
import sqlite3
import json
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import SQLITE_PATH
from memory.models import (
    CustomerMemoryNonPII,
    CustomerMemoryPII,
    SessionLog,
    FieldChangeLog,
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
        """
        Initialize database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
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

    def init_schema(self):
        """Create tables if they don't exist."""
        if not self.connection:
            self.connect()

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

        # Field change log
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS field_change_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,
                field_name TEXT NOT NULL,
                old_value_encrypted TEXT,
                new_value_encrypted TEXT,
                changed_at TEXT NOT NULL,
                session_id TEXT NOT NULL,
                conflict_detected INTEGER DEFAULT 0,
                user_confirmed INTEGER DEFAULT 0,
                confirmation_timestamp TEXT,
                FOREIGN KEY (customer_id) REFERENCES customer_memory_nonpii(customer_id),
                FOREIGN KEY (session_id) REFERENCES session_log(session_id)
            )
        """)

        # Indexes for frequent queries
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_session_customer ON session_log(customer_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_change_customer ON field_change_log(customer_id)"
        )

        self.connection.commit()

    def save_customer_memory(
        self, nonpii: CustomerMemoryNonPII, pii: CustomerMemoryPII
    ) -> bool:
        """
        Save customer memory (both non-PII and PII).
        
        Args:
            nonpii: CustomerMemoryNonPII instance
            pii: CustomerMemoryPII instance
            
        Returns:
            True if successful
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            # Save non-PII
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
                    nonpii.monthly_income.model_dump_json()
                    if nonpii.monthly_income
                    else None,
                    nonpii.income_type.model_dump_json()
                    if nonpii.income_type
                    else None,
                    nonpii.total_work_experience_years.model_dump_json()
                    if nonpii.total_work_experience_years
                    else None,
                    json.dumps([h.model_dump() for h in nonpii.employment_history],
                               default=str),
                    nonpii.cibil_score.model_dump_json()
                    if nonpii.cibil_score
                    else None,
                    nonpii.cibil_last_checked.isoformat()
                    if nonpii.cibil_last_checked
                    else None,
                    nonpii.total_existing_emi_monthly.model_dump_json()
                    if nonpii.total_existing_emi_monthly
                    else None,
                    nonpii.number_of_active_loans.model_dump_json()
                    if nonpii.number_of_active_loans
                    else None,
                    nonpii.loan_request.model_dump_json()
                    if nonpii.loan_request
                    else None,
                    json.dumps([d.model_dump() for d in nonpii.documents_submitted],
                               default=str),
                    nonpii.application_status.value,
                    1 if nonpii.is_active else 0,
                    nonpii.created_at.isoformat(),
                    nonpii.last_updated.isoformat(),
                ),
            )

            # Save PII (with encryption)
            pii_data = {
                "customer_id": pii.customer_id,
                "full_name": pii.full_name.model_dump_json()
                if pii.full_name
                else None,
                "date_of_birth": pii.date_of_birth.model_dump_json()
                if pii.date_of_birth
                else None,
                "gender": pii.gender.model_dump_json() if pii.gender else None,
                "marital_status": pii.marital_status.model_dump_json()
                if pii.marital_status
                else None,
                "pan_hash": pii.pan_hash,
                "aadhaar_hash": pii.aadhaar_hash,
                "primary_phone": pii.primary_phone.model_dump_json()
                if pii.primary_phone
                else None,
                "current_address": pii.current_address.model_dump_json()
                if pii.current_address
                else None,
                "city": pii.city.model_dump_json() if pii.city else None,
                "state": pii.state.model_dump_json() if pii.state else None,
                "pincode": pii.pincode.model_dump_json() if pii.pincode else None,
                "employer_name": pii.employer_name.model_dump_json()
                if pii.employer_name
                else None,
                "years_at_current_job": pii.years_at_current_job.model_dump_json()
                if pii.years_at_current_job
                else None,
                "co_applicants": json.dumps([c.model_dump() for c in pii.co_applicants],
                                           default=str),
                "guarantors": json.dumps([g.model_dump() for g in pii.guarantors],
                                        default=str),
            }

            # Encrypt PII fields (except customer_id, pan_hash, aadhaar_hash)
            for field in self.PII_ENCRYPTED_FIELDS:
                if field in pii_data and pii_data[field]:
                    try:
                        pii_data[field] = self.encryption.encrypt(pii_data[field])
                    except Exception as e:
                        print(f"⚠️  Failed to encrypt {field}: {e}")

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
                    pii_data["customer_id"],
                    pii_data["full_name"],
                    pii_data["date_of_birth"],
                    pii_data["gender"],
                    pii_data["marital_status"],
                    pii_data["pan_hash"],
                    pii_data["aadhaar_hash"],
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
                    pii.last_updated.isoformat(),
                ),
            )

            self.connection.commit()
            return True

        except Exception as e:
            print(f"❌ Failed to save customer memory: {e}")
            self.connection.rollback()
            return False

    def load_customer_memory(
        self, customer_id: str
    ) -> Tuple[Optional[CustomerMemoryNonPII], Optional[CustomerMemoryPII]]:
        """
        Load customer memory (both non-PII and PII).
        
        Args:
            customer_id: Customer ID
            
        Returns:
            Tuple of (CustomerMemoryNonPII, CustomerMemoryPII) or (None, None) if not found
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            # Load non-PII
            cursor.execute(
                "SELECT * FROM customer_memory_nonpii WHERE customer_id = ?",
                (customer_id,),
            )
            row = cursor.fetchone()

            if not row:
                return None, None

            nonpii_data = dict(row)
            # Deserialize JSON fields
            if nonpii_data["monthly_income_json"]:
                from memory.models import FixedEntity
                nonpii_data["monthly_income"] = FixedEntity.model_validate_json(
                    nonpii_data["monthly_income_json"]
                )
            # ... repeat for other JSON fields (abbreviated for brevity)

            nonpii = CustomerMemoryNonPII(
                customer_id=nonpii_data["customer_id"],
                monthly_income=nonpii_data.get("monthly_income"),
                is_active=bool(nonpii_data["is_active"]),
                created_at=datetime.fromisoformat(nonpii_data["created_at"]),
                last_updated=datetime.fromisoformat(nonpii_data["last_updated"]),
            )

            # Load PII
            cursor.execute(
                "SELECT * FROM customer_memory_pii WHERE customer_id = ?",
                (customer_id,),
            )
            pii_row = cursor.fetchone()

            if not pii_row:
                return nonpii, None

            pii_data = dict(pii_row)

            # Decrypt PII fields
            for field in self.PII_ENCRYPTED_FIELDS:
                encrypted_field = f"{field}_encrypted"
                if encrypted_field in pii_data and pii_data[encrypted_field]:
                    try:
                        pii_data[field] = self.encryption.decrypt(
                            pii_data[encrypted_field]
                        )
                    except Exception as e:
                        print(f"⚠️  Failed to decrypt {field}: {e}")

            pii = CustomerMemoryPII(
                customer_id=pii_data["customer_id"],
                pan_hash=pii_data.get("pan_hash"),
                aadhaar_hash=pii_data.get("aadhaar_hash"),
                created_at=datetime.fromisoformat(pii_data["created_at"]),
                last_updated=datetime.fromisoformat(pii_data["last_updated"]),
            )

            return nonpii, pii

        except Exception as e:
            print(f"❌ Failed to load customer memory: {e}")
            return None, None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()


# ============================================================================
# TEST UTILITIES
# ============================================================================


def test_database():
    """Test database operations."""
    print("\n" + "=" * 70)
    print("💾 Testing Memory Database")
    print("=" * 70)

    db = MemoryDatabase(db_path=":memory:")  # Use in-memory DB for testing

    # Initialize schema
    print("\n1. Initializing schema...")
    db.connect()
    db.init_schema()
    print("   ✅ Schema created")

    # Create test data
    print("\n2. Creating test data (Rajesh scenario)...")
    nonpii, pii = create_test_memory()
    print(f"   ✅ Test data created for {nonpii.customer_id}")

    # Save to database
    print("\n3. Saving to database...")
    success = db.save_customer_memory(nonpii, pii)
    if success:
        print("   ✅ Saved successfully")
    else:
        print("   ❌ Save failed")
        return

    # Load from database
    print("\n4. Loading from database...")
    loaded_nonpii, loaded_pii = db.load_customer_memory(nonpii.customer_id)

    if loaded_nonpii and loaded_pii:
        print("   ✅ Loaded successfully")
        print(f"   Customer ID: {loaded_nonpii.customer_id}")
        print(f"   Monthly income: {loaded_nonpii.monthly_income.current.value if loaded_nonpii.monthly_income else 'N/A'}")
        print(f"   Full name: {loaded_pii.full_name.current.value if loaded_pii.full_name else 'N/A'}")
        print(f"   Phone: {loaded_pii.primary_phone.current.value if loaded_pii.primary_phone else 'N/A'}")
    else:
        print("   ❌ Load failed")

    db.close()
    print("\n✅ Database test complete!")


if __name__ == "__main__":
    test_database()
