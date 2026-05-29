"""
integrations/encryption.py — Fernet helpers for encrypting stored tokens.
"""

from __future__ import annotations

import os
import traceback

try:
    from cryptography.fernet import Fernet
except Exception:
    print("Failed to import Fernet in integrations.encryption", flush=True)
    traceback.print_exc()
    raise


class EncryptionError(RuntimeError):
    """Raised when encryption is configured incorrectly."""


def encrypt_token(token: str) -> str:
    """Encrypt a token for storage."""
    if not isinstance(token, str) or not token:
        raise EncryptionError("Token must be a non-empty string")
    cipher = _get_cipher()
    return cipher.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_token(encrypted: str) -> str:
    """Decrypt a previously encrypted token."""
    if not isinstance(encrypted, str) or not encrypted:
        raise EncryptionError("Encrypted token must be a non-empty string")
    cipher = _get_cipher()
    return cipher.decrypt(encrypted.encode("utf-8")).decode("utf-8")


def _get_cipher() -> Fernet:
    key = os.getenv("ENCRYPTION_KEY")
    if not key:
        raise EncryptionError("ENCRYPTION_KEY is not set")
    try:
        return Fernet(key.encode("utf-8"))
    except Exception as exc:
        raise EncryptionError("ENCRYPTION_KEY is invalid") from exc
