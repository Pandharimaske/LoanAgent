"""
User authentication SQLite operations.
Handles user registration, login, and session management.
"""

import sys
import json
import sqlite3
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import SQLITE_PATH
from auth.models import User, UserCreate, UserSession
from auth.utils import PasswordManager, UserIDGenerator, TokenManager


class UserDatabase:
    """SQLite database manager for user authentication."""

    def __init__(self, db_path: str = SQLITE_PATH):
        """
        Initialize user database manager.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.connection = None

    def connect(self) -> sqlite3.Connection:
        """Connect to database."""
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        return self.connection

    def close(self):
        """Close database connection."""
        if self.connection:
            self.connection.close()

    def init_user_schema(self):
        """Create user-related tables if they don't exist."""
        if not self.connection:
            self.connect()

        cursor = self.connection.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'customer',
                status TEXT DEFAULT 'active',
                is_verified INTEGER DEFAULT 0,
                customer_id TEXT UNIQUE,
                created_at TEXT NOT NULL,
                last_login TEXT
            )
        """)

        # User sessions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                customer_id TEXT,
                logged_in_at TEXT NOT NULL,
                last_activity TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                messages TEXT DEFAULT '[]',
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Migrate existing table: add messages column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE user_sessions ADD COLUMN messages TEXT DEFAULT '[]'")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Migrate existing table: add summary column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE user_sessions ADD COLUMN summary TEXT DEFAULT NULL")
        except sqlite3.OperationalError:
            pass  # Column already exists

        # Indexes for frequent queries
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_user ON user_sessions(user_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sessions_active ON user_sessions(is_active)"
        )

        self.connection.commit()

    def register_user(
        self,
        username: str,
        email: str,
        name: str,
        password: str,
        customer_id: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Register a new user.
        
        Args:
            username: Username
            email: Email address
            name: Full name
            password: Plain text password
            customer_id: Optional customer ID (for customer users)
            
        Returns:
            Tuple of (success: bool, user_id: str, error: str)
        """
        if not self.connection:
            self.connect()

        try:
            # Generate user ID from username
            user_id = UserIDGenerator.generate_user_id(username)

            # Hash password
            password_hash = PasswordManager.hash_password(password)

            # Insert user
            cursor = self.connection.cursor()
            cursor.execute(
                """
                INSERT INTO users (
                    user_id, username, email, name, password_hash,
                    customer_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    email,
                    name,
                    password_hash,
                    customer_id,
                    datetime.now().isoformat(),
                ),
            )

            self.connection.commit()
            return True, user_id, None

        except sqlite3.IntegrityError as e:
            if "username" in str(e):
                return False, None, "Username already exists"
            elif "email" in str(e):
                return False, None, "Email already exists"
            else:
                return False, None, str(e)
        except Exception as e:
            return False, None, str(e)

    def login(
        self, email: str, password: str, expires_in_hours: int = 24
    ) -> Tuple[bool, Optional[UserSession], Optional[str]]:
        """
        Authenticate user and create session.
        
        Args:
            email: Email address
            password: Plain text password
            expires_in_hours: Session expiry time
            
        Returns:
            Tuple of (success: bool, session: UserSession, error: str)
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            # Fetch user by email
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()

            if not row:
                return False, None, "Invalid email or password"

            user = dict(row)

            # Verify password
            if not PasswordManager.verify_password(password, user["password_hash"]):
                return False, None, "Invalid email or password"

            # Create session
            session_id = UserIDGenerator.generate_session_id()
            now = datetime.now()
            expires_at = now + timedelta(hours=expires_in_hours)

            cursor.execute(
                """
                INSERT INTO user_sessions (
                    session_id, user_id, username, customer_id,
                    logged_in_at, last_activity, expires_at, is_active,
                    messages
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    user["user_id"],
                    user["username"],
                    user["customer_id"],
                    now.isoformat(),
                    now.isoformat(),
                    expires_at.isoformat(),
                    1,
                    json.dumps([]),
                ),
            )

            # Update last login
            cursor.execute(
                "UPDATE users SET last_login = ? WHERE user_id = ?",
                (now.isoformat(), user["user_id"]),
            )

            self.connection.commit()

            # Create session object
            session = UserSession(
                session_id=session_id,
                user_id=user["user_id"],
                email=user["email"],
                customer_id=user["customer_id"],
                logged_in_at=now,
                last_activity=now,
                expires_at=expires_at,
                is_active=True,
                messages=[],
            )

            return True, session, None

        except Exception as e:
            return False, None, str(e)

    def get_user(self, user_id: str) -> Optional[User]:
        """
        Get user by ID.
        
        Args:
            user_id: User ID
            
        Returns:
            User object or None if not found
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()
            cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()

            if not row:
                return None

            user_data = dict(row)
            return User(
                user_id=user_data["user_id"],
                username=user_data["username"],
                email=user_data["email"],
                name=user_data["name"],
                customer_id=user_data["customer_id"],
                created_at=datetime.fromisoformat(user_data["created_at"]),
                last_login=datetime.fromisoformat(user_data["last_login"])
                if user_data["last_login"]
                else None,
            )

        except Exception as e:
            print(f"❌ Failed to get user: {e}")
            return None

    def get_session(self, session_id: str) -> Optional[UserSession]:
        """
        Get session by ID.
        
        Args:
            session_id: Session ID
            
        Returns:
            UserSession object or None
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()
            # JOIN with users to get email (user_sessions stores username, not email)
            cursor.execute(
                """
                SELECT s.*, u.email
                FROM user_sessions s
                JOIN users u ON s.user_id = u.user_id
                WHERE s.session_id = ?
                """,
                (session_id,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            session_data = dict(row)

            # Check if expired
            expires_at = datetime.fromisoformat(session_data["expires_at"])
            if datetime.now() > expires_at:
                # Mark as inactive
                cursor.execute(
                    "UPDATE user_sessions SET is_active = 0 WHERE session_id = ?",
                    (session_id,),
                )
                self.connection.commit()
                return None

            raw_messages = session_data.get("messages") or "[]"
            try:
                messages = json.loads(raw_messages)
            except (json.JSONDecodeError, TypeError):
                messages = []

            return UserSession(
                session_id=session_data["session_id"],
                user_id=session_data["user_id"],
                email=session_data["email"],          # from JOIN with users table
                customer_id=session_data["customer_id"],
                logged_in_at=datetime.fromisoformat(
                    session_data["logged_in_at"]
                ),
                last_activity=datetime.fromisoformat(
                    session_data["last_activity"]
                ),
                expires_at=expires_at,
                is_active=bool(session_data["is_active"]),
                messages=messages,
                summary=session_data.get("summary"),   # LLM-generated summary (may be None)
            )

        except Exception as e:
            print(f"❌ Failed to get session: {e}")
            return None

    def logout(self, session_id: str) -> bool:
        """
        Logout user (invalidate session).
        
        Args:
            session_id: Session ID to invalidate
            
        Returns:
            True if successful
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE user_sessions SET is_active = 0 WHERE session_id = ?",
                (session_id,),
            )
            self.connection.commit()
            return True
        except Exception as e:
            print(f"❌ Failed to logout: {e}")
            return False

    def save_session_messages(
        self, session_id: str, messages: list
    ) -> bool:
        """
        Persist the conversation messages list for a session.

        Serialises messages to JSON and writes to the messages column of
        user_sessions. Safe to call after every graph turn.

        Args:
            session_id: The session whose messages to save.
            messages:   List of message dicts (role/content/timestamp).

        Returns:
            True on success, False on failure.
        """
        if not self.connection:
            self.connect()
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE user_sessions SET messages = ? WHERE session_id = ?",
                (json.dumps(messages), session_id),
            )
            self.connection.commit()
            return True
        except Exception as e:
            print(f"❌ Failed to save session messages: {e}")
            return False

    def get_session_messages(self, session_id: str) -> list:
        """
        Load the conversation messages list for a session.

        Reads the messages column from user_sessions and deserialises JSON.
        Returns an empty list if the session doesn't exist or has no messages.

        Args:
            session_id: The session to load messages for.

        Returns:
            List of message dicts, or [] on error / not found.
        """
        if not self.connection:
            self.connect()
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT messages FROM user_sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                return []
            raw = dict(row).get("messages") or "[]"
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return []
        except Exception as e:
            print(f"❌ Failed to get session messages: {e}")
            return []

    def save_session_summary(self, session_id: str, summary: str) -> bool:
        """
        Persist the LLM-generated context summary for a session.

        Called by check_token_threshold when the token limit is hit so that
        the summary survives server restarts and can be re-injected into context
        when the session is resumed.

        Args:
            session_id: The session to update.
            summary:    The compact LLM-generated summary text.

        Returns:
            True on success, False on failure.
        """
        if not self.connection:
            self.connect()
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "UPDATE user_sessions SET summary = ? WHERE session_id = ?",
                (summary, session_id),
            )
            self.connection.commit()
            return True
        except Exception as e:
            print(f"❌ Failed to save session summary: {e}")
            return False

    def get_session_summary(self, session_id: str) -> Optional[str]:
        """
        Load the LLM-generated summary for a session, or None if absent.

        Args:
            session_id: The session to query.

        Returns:
            Summary string, or None if not set.
        """
        if not self.connection:
            self.connect()
        try:
            cursor = self.connection.cursor()
            cursor.execute(
                "SELECT summary FROM user_sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return dict(row).get("summary")  # may be None
        except Exception as e:
            print(f"❌ Failed to get session summary: {e}")
            return None


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


def test_user_database():
    """Test user operations."""
    print("\n" + "=" * 70)
    print("👥 Testing User Database")
    print("=" * 70)

    db = UserDatabase(db_path=":memory:")  # Use in-memory DB

    # Initialize schema
    print("\n1. Initializing schema...")
    db.connect()
    db.init_user_schema()
    print("   ✅ Schema created")

    # Register user
    print("\n2. Registering user...")
    success, user_id, error = db.register_user(
        username="rajesh_kumar",
        email="rajesh@example.com",
        name="Rajesh Kumar",
        password="SecurePass123",
        customer_id="RAJESH_001",
    )

    if success:
        print(f"   ✅ User registered: {user_id}")
    else:
        print(f"   ❌ Registration failed: {error}")
        return

    # Test duplicate registration
    print("\n3. Testing duplicate username...")
    success, _, error = db.register_user(
        username="rajesh_kumar",
        email="another@example.com",
        name="Another User",
        password="SecurePass123",
    )
    if not success:
        print(f"   ✅ Correctly rejected: {error}")
    else:
        print(f"   ❌ Should have rejected duplicate")

    # Login
    print("\n4. Testing login...")
    success, session, error = db.login("rajesh_kumar", "SecurePass123")

    if success and session:
        print(f"   ✅ Login successful")
        print(f"   Session ID: {session.session_id[:20]}...")
        print(f"   Expires: {session.expires_at}")
    else:
        print(f"   ❌ Login failed: {error}")
        return

    # Get user
    print("\n5. Getting user...")
    user = db.get_user(user_id)
    if user:
        print(f"   ✅ User fetched: {user.name} ({user.username})")
        print(f"   Customer ID: {user.customer_id}")
    else:
        print(f"   ❌ Failed to fetch user")

    # Get session
    print("\n6. Getting session...")
    fetched_session = db.get_session(session.session_id)
    if fetched_session and fetched_session.is_active:
        print(f"   ✅ Session active: {fetched_session.session_id[:20]}...")
    else:
        print(f"   ❌ Session not found or expired")

    # Logout
    print("\n7. Testing logout...")
    logout_success = db.logout(session.session_id)
    if logout_success:
        print(f"   ✅ Logout successful")
        # Check session is now inactive
        session_after = db.get_session(session.session_id)
        if not session_after:
            print(f"   ✅ Session invalidated")
    else:
        print(f"   ❌ Logout failed")

    db.close()
    print("\n✅ User database tests complete!")


if __name__ == "__main__":
    test_user_database()
