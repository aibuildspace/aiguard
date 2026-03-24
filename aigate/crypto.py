"""
Encryption helpers for storing upstream API keys at rest.
Uses Fernet (AES-128-CBC + HMAC-SHA256) from the cryptography library.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from aigate.config import settings


def _get_fernet() -> Fernet:
    key = settings.encryption_key
    if not key:
        raise RuntimeError(
            "GUARD_ENCRYPTION_KEY is not set. "
            "Run 'aigate start' or 'aigate startdev' to auto-generate it, "
            "or set it manually: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    # Fernet needs a 32-byte URL-safe base64 key. If user passed a raw hex string, derive it.
    raw = key.encode()
    if len(raw) == 44 and raw.endswith(b"="):
        fernet_key = raw  # already URL-safe base64
    else:
        # Derive a 32-byte key from whatever was given
        digest = hashlib.sha256(raw).digest()
        fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt(plaintext: str) -> str:
    """Encrypt a plaintext string. Returns URL-safe base64 ciphertext."""
    return _get_fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    """Decrypt a ciphertext string. Raises cryptography.fernet.InvalidToken on failure."""
    return _get_fernet().decrypt(ciphertext.encode()).decode()
