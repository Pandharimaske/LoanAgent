"""
Encryption utilities for PII field protection.
All PII is encrypted before writing to SQLite, decrypted on read.
"""

import sys
from pathlib import Path
from typing import Optional
import json
from cryptography.fernet import Fernet

sys.path.insert(0, str(Path(__file__).parent.parent))


class EncryptionManager:
    """
    Handle encryption/decryption of sensitive data.
    Uses Fernet (symmetric encryption) from cryptography library.
    """

    def __init__(self, encryption_key: Optional[str] = None):
        """
        Initialize encryption manager.
        
        Args:
            encryption_key: Base64-encoded Fernet key. If None, looks for DB_ENCRYPTION_KEY env var.
                           If that's also missing, generates a new key (INSECURE - use only for dev).
        """
        if encryption_key:
            self.key = encryption_key.encode()
        else:
            import os
            env_key = os.getenv("DB_ENCRYPTION_KEY")
            if env_key:
                self.key = env_key.encode()
            else:
                # Generate a new key (only for dev/testing)
                print(
                    "⚠️  No DB_ENCRYPTION_KEY found. Generating new key."
                    "\n   For production, set DB_ENCRYPTION_KEY env var."
                )
                self.key = Fernet.generate_key()
                print(f"\n   Generated key (save this):\n   {self.key.decode()}\n")

        self.cipher = Fernet(self.key)

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new encryption key.
        Call this once during setup, then save to env var.
        
        Returns:
            Base64-encoded Fernet key as string
        """
        return Fernet.generate_key().decode()

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext string.
        
        Args:
            plaintext: String to encrypt
            
        Returns:
            Encrypted string (base64-encoded)
            
        Raises:
            ValueError: If plaintext is None or empty
        """
        if not plaintext:
            raise ValueError("Cannot encrypt empty string")

        plaintext_bytes = plaintext.encode("utf-8")
        encrypted_bytes = self.cipher.encrypt(plaintext_bytes)
        return encrypted_bytes.decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt an encrypted string.
        
        Args:
            ciphertext: Encrypted string (base64-encoded)
            
        Returns:
            Decrypted plaintext string
            
        Raises:
            cryptography.fernet.InvalidToken: If decryption fails or tampering detected
        """
        if not ciphertext:
            raise ValueError("Cannot decrypt empty string")

        ciphertext_bytes = ciphertext.encode("utf-8")
        plaintext_bytes = self.cipher.decrypt(ciphertext_bytes)
        return plaintext_bytes.decode("utf-8")

    def encrypt_dict(self, data: dict, keys_to_encrypt: list) -> dict:
        """
        Encrypt specific keys in a dictionary.
        Non-encrypted keys remain as-is.
        
        Args:
            data: Dictionary with mixed encrypted/plain fields
            keys_to_encrypt: List of key names to encrypt
            
        Returns:
            New dict with specified keys encrypted
        """
        encrypted = data.copy()
        for key in keys_to_encrypt:
            if key in encrypted and encrypted[key]:
                try:
                    encrypted[key] = self.encrypt(str(encrypted[key]))
                except Exception as e:
                    print(f"⚠️  Failed to encrypt key '{key}': {e}")
                    # Keep original if encryption fails
        return encrypted

    def decrypt_dict(self, data: dict, keys_to_decrypt: list) -> dict:
        """
        Decrypt specific keys in a dictionary.
        
        Args:
            data: Dictionary with encrypted fields
            keys_to_decrypt: List of key names to decrypt
            
        Returns:
            New dict with specified keys decrypted
        """
        decrypted = data.copy()
        for key in keys_to_decrypt:
            if key in decrypted and decrypted[key]:
                try:
                    decrypted[key] = self.decrypt(decrypted[key])
                except Exception as e:
                    print(f"⚠️  Failed to decrypt key '{key}': {e}")
                    # Keep encrypted if decryption fails (safer than losing data)
        return decrypted

    def encrypt_json(self, data: dict, keys_to_encrypt: list) -> str:
        """
        Serialize dict to JSON with selected fields encrypted.
        
        Args:
            data: Dictionary to serialize
            keys_to_encrypt: Keys whose values will be encrypted
            
        Returns:
            JSON string with encrypted fields
        """
        encrypted = self.encrypt_dict(data, keys_to_encrypt)
        return json.dumps(encrypted, default=str)

    def decrypt_json(self, json_str: str, keys_to_decrypt: list) -> dict:
        """
        Deserialize JSON with selected fields decrypted.
        
        Args:
            json_str: JSON string with encrypted fields
            keys_to_decrypt: Keys to decrypt after parsing
            
        Returns:
            Dictionary with decrypted fields
        """
        data = json.loads(json_str)
        decrypted = self.decrypt_dict(data, keys_to_decrypt)
        return decrypted


# ============================================================================
# GLOBAL MANAGER (singleton pattern)
# ============================================================================

_encryption_manager: Optional[EncryptionManager] = None


def get_encryption_manager() -> EncryptionManager:
    """Get or create the global encryption manager."""
    global _encryption_manager
    if _encryption_manager is None:
        _encryption_manager = EncryptionManager()
    return _encryption_manager


def set_encryption_key(key: str) -> None:
    """Set a custom encryption key (must be called before get_encryption_manager)."""
    global _encryption_manager
    _encryption_manager = EncryptionManager(encryption_key=key)


# ============================================================================
# TEST UTILITIES
# ============================================================================


def test_encryption():
    """Test encryption/decryption."""
    print("\n" + "=" * 70)
    print("🔐 Testing Encryption Manager")
    print("=" * 70)

    # Generate a new key
    key = EncryptionManager.generate_key()
    print(f"\n✅ Generated key:\n   {key}")

    # Create manager with that key
    manager = EncryptionManager(encryption_key=key)

    # Test string encryption
    test_data = {
        "phone": "9876543210",
        "pan": "ABCDE1234F",
        "address": "123 Main Street, Bangalore",
    }

    print(f"\n📝 Original data:")
    print(f"   {test_data}")

    # Encrypt selected fields
    encrypted = manager.encrypt_dict(test_data, ["phone", "pan"])
    print(f"\n🔒 Encrypted (selected keys):")
    print(f"   {encrypted}")

    # Decrypt
    decrypted = manager.decrypt_dict(encrypted, ["phone", "pan"])
    print(f"\n🔓 Decrypted:")
    print(f"   {decrypted}")

    # Verify
    assert decrypted == test_data, "Decryption failed!"
    print(f"\n✅ Encryption/decryption working correctly")

    # Test JSON mode
    print(f"\n📋 JSON Mode:")
    json_encrypted = manager.encrypt_json(test_data, ["phone", "pan"])
    print(f"   Encrypted JSON:\n   {json_encrypted}")

    json_decrypted = manager.decrypt_json(json_encrypted, ["phone", "pan"])
    print(f"   Decrypted: {json_decrypted}")
    assert json_decrypted == test_data, "JSON encryption/decryption failed!"

    print(f"\n✅ All encryption tests passed!")


def test_global_manager():
    """Test singleton pattern."""
    print("\n" + "=" * 70)
    print("🔑 Testing Global Encryption Manager")
    print("=" * 70)

    # First call creates instance
    mgr1 = get_encryption_manager()
    print(f"\n✅ Created global manager: {type(mgr1).__name__}")

    # Second call returns same instance
    mgr2 = get_encryption_manager()
    print(f"✅ Subsequent call returns same instance: {mgr1 is mgr2}")

    # Set custom key
    key = EncryptionManager.generate_key()
    set_encryption_key(key)
    mgr3 = get_encryption_manager()
    print(f"✅ After set_encryption_key, new instance created: {mgr1 is not mgr3}")


if __name__ == "__main__":
    test_encryption()
    test_global_manager()
