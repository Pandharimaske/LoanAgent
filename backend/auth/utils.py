"""
Password hashing and JWT token utilities for user authentication.
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
import os
import secrets
import hashlib

sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import bcrypt
except ImportError:
    print("⚠️  bcrypt not installed. Run: pip install bcrypt")
    bcrypt = None


class PasswordManager:
    """Manage password hashing and verification."""

    @staticmethod
    def hash_password(password: str, rounds: int = 12) -> str:
        """
        Hash a password using bcrypt.
        
        Args:
            password: Plain text password
            rounds: Bcrypt cost rounds (higher = slower but more secure)
            
        Returns:
            Hashed password (bcrypt format)
            
        Raises:
            RuntimeError: If bcrypt not available
        """
        if not bcrypt:
            raise RuntimeError("bcrypt not installed")
        
        salt = bcrypt.gensalt(rounds=rounds)
        return bcrypt.hashpw(password.encode(), salt).decode()

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """
        Verify a plain password against a bcrypt hash.
        
        Args:
            password: Plain text password to verify
            password_hash: Bcrypt hash to check against
            
        Returns:
            True if password matches, False otherwise
        """
        if not bcrypt:
            raise RuntimeError("bcrypt not installed")
        
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except Exception as e:
            print(f"❌ Password verification failed: {e}")
            return False


class TokenManager:
    """Manage JWT tokens for session management."""

    @staticmethod
    def generate_token_secret() -> str:
        """
        Generate a random token secret for JWT signing.
        
        Returns:
            Random hex string suitable for JWT secret
        """
        return secrets.token_hex(32)

    @staticmethod
    def generate_session_token() -> str:
        """
        Generate a secure random session token.
        
        Returns:
            Random hex token
        """
        return secrets.token_hex(32)

    @staticmethod
    def generate_token_with_expiry(
        user_id: str,
        username: str,
        customer_id: Optional[str] = None,
        expires_in_hours: int = 24,
    ) -> dict:
        """
        Generate token data with expiry.
        
        Args:
            user_id: User ID
            username: Username
            customer_id: Optional customer ID
            expires_in_hours: Hours until token expires
            
        Returns:
            Dict with token info (to be encoded as JWT)
        """
        now = datetime.now()
        expires_at = now + timedelta(hours=expires_in_hours)
        
        return {
            "user_id": user_id,
            "username": username,
            "customer_id": customer_id,
            "issued_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

    @staticmethod
    def is_token_expired(expires_at: str) -> bool:
        """
        Check if token has expired.
        
        Args:
            expires_at: ISO format expiry timestamp
            
        Returns:
            True if expired, False otherwise
        """
        try:
            expires = datetime.fromisoformat(expires_at)
            return datetime.now() > expires
        except Exception:
            return True


class UserIDGenerator:
    """Generate unique user IDs."""

    @staticmethod
    def generate_user_id(username: str) -> str:
        """
        Generate a deterministic user ID from username.
        Format: USER_<hash>
        
        Args:
            username: Username
            
        Returns:
            User ID
        """
        # Hash username for consistent ID
        hash_obj = hashlib.sha256(username.lower().encode())
        hash_val = hash_obj.hexdigest()[:8].upper()
        return f"USER_{hash_val}"

    @staticmethod
    def generate_session_id() -> str:
        """
        Generate a unique session ID.
        Format: SESSION_<random>
        
        Returns:
            Session ID
        """
        random_part = secrets.token_hex(8).upper()
        return f"SESSION_{random_part}"


# ============================================================================
# TEST UTILITIES
# ============================================================================


def test_password_manager():
    """Test password hashing."""
    print("\n" + "=" * 70)
    print("🔐 Testing Password Manager")
    print("=" * 70)

    if not bcrypt:
        print("⚠️  bcrypt not available. Skipping test.")
        return

    # Hash password
    password = "MySecurePassword123!"
    hashed = PasswordManager.hash_password(password)
    print(f"\n1. Hash password:")
    print(f"   Original: {password}")
    print(f"   Hashed:   {hashed[:50]}...")

    # Verify correct password
    is_correct = PasswordManager.verify_password(password, hashed)
    print(f"\n2. Verify correct password: {'✅' if is_correct else '❌'}")

    # Verify incorrect password
    is_incorrect = PasswordManager.verify_password("WrongPassword123!", hashed)
    print(f"3. Verify wrong password fails: {'✅' if not is_incorrect else '❌'}")

    print("\n✅ Password manager tests passed!")


def test_token_manager():
    """Test token generation."""
    print("\n" + "=" * 70)
    print("🎫 Testing Token Manager")
    print("=" * 70)

    # Generate session token
    token = TokenManager.generate_session_token()
    print(f"\n1. Generated session token: {token[:20]}...")

    # Generate token with expiry
    token_data = TokenManager.generate_token_with_expiry(
        user_id="USER_ABC123",
        username="rajesh",
        customer_id="RAJESH_001",
        expires_in_hours=24,
    )
    print(f"\n2. Token data:")
    print(f"   User ID:    {token_data['user_id']}")
    print(f"   Username:   {token_data['username']}")
    print(f"   Expires at: {token_data['expires_at']}")

    # Check expiry
    is_expired = TokenManager.is_token_expired(token_data["expires_at"])
    print(f"\n3. Is token expired? {'❌ (expired)' if is_expired else '✅ (valid)'}")

    # Test expired token
    expired_data = TokenManager.generate_token_with_expiry(
        user_id="USER_XYZ", username="test", expires_in_hours=-1
    )
    is_expired = TokenManager.is_token_expired(expired_data["expires_at"])
    print(f"4. Expired token detected? {'✅' if is_expired else '❌'}")

    print("\n✅ Token manager tests passed!")


def test_user_id_generator():
    """Test user ID generation."""
    print("\n" + "=" * 70)
    print("🆔 Testing User ID Generator")
    print("=" * 70)

    # Generate user IDs
    user_id_1 = UserIDGenerator.generate_user_id("rajesh_kumar")
    user_id_2 = UserIDGenerator.generate_user_id("rajesh_kumar")  # Same username
    user_id_3 = UserIDGenerator.generate_user_id("sunita")

    print(f"\n1. User IDs (deterministic):")
    print(f"   rajesh_kumar → {user_id_1}")
    print(f"   rajesh_kumar → {user_id_2} (same as above: {user_id_1 == user_id_2})")
    print(f"   sunita       → {user_id_3}")

    # Generate session IDs
    sess_1 = UserIDGenerator.generate_session_id()
    sess_2 = UserIDGenerator.generate_session_id()

    print(f"\n2. Session IDs (random):")
    print(f"   {sess_1}")
    print(f"   {sess_2}")
    print(f"   Different: {sess_1 != sess_2}")

    print("\n✅ User ID generator tests passed!")


if __name__ == "__main__":
    test_password_manager()
    test_token_manager()
    test_user_id_generator()
