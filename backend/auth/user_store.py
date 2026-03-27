"""
User authentication SQLite operations.
Handles user registration, login, and session management.
"""

import sys
import sqlite3
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import SQLITE_PATH
from auth.models import User, UserCreate, UserRole, UserStatus, UserSession
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
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

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
                    role, status, customer_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    email,
                    name,
                    password_hash,
                    UserRole.CUSTOMER.value,
                    UserStatus.ACTIVE.value,
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
        self, username: str, password: str, expires_in_hours: int = 24
    ) -> Tuple[bool, Optional[UserSession], Optional[str]]:
        """
        Authenticate user and create session.
        
        Args:
            username: Username
            password: Plain text password
            expires_in_hours: Session expiry time
            
        Returns:
            Tuple of (success: bool, session: UserSession, error: str)
        """
        if not self.connection:
            self.connect()

        try:
            cursor = self.connection.cursor()

            # Fetch user by username
            cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
            row = cursor.fetchone()

            if not row:
                return False, None, "Invalid username or password"

            user = dict(row)

            # Verify password
            if not PasswordManager.verify_password(password, user["password_hash"]):
                return False, None, "Invalid username or password"

            # Check if user is active
            if user["status"] != UserStatus.ACTIVE.value:
                return False, None, f"User account is {user['status']}"

            # Create session
            session_id = UserIDGenerator.generate_session_id()
            now = datetime.now()
            expires_at = now + timedelta(hours=expires_in_hours)

            cursor.execute(
                """
                INSERT INTO user_sessions (
                    session_id, user_id, username, customer_id,
                    logged_in_at, last_activity, expires_at, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                username=user["username"],
                customer_id=user["customer_id"],
                logged_in_at=now,
                last_activity=now,
                expires_at=expires_at,
                is_active=True,
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
                role=UserRole(user_data["role"]),
                status=UserStatus(user_data["status"]),
                is_verified=bool(user_data["is_verified"]),
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
            cursor.execute(
                "SELECT * FROM user_sessions WHERE session_id = ?", (session_id,)
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

            return UserSession(
                session_id=session_data["session_id"],
                user_id=session_data["user_id"],
                username=session_data["username"],
                customer_id=session_data["customer_id"],
                logged_in_at=datetime.fromisoformat(
                    session_data["logged_in_at"]
                ),
                last_activity=datetime.fromisoformat(
                    session_data["last_activity"]
                ),
                expires_at=expires_at,
                is_active=bool(session_data["is_active"]),
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
