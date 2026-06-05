"""Fernet-based encryption for sensitive data like Edsby credentials."""
import base64
import hashlib
from cryptography.fernet import Fernet
from app.core.config import settings


def _get_fernet() -> Fernet:
    """Derive a Fernet key from JWT_SECRET_KEY."""
    # Fernet needs 32 bytes base64-encoded = 32 url-safe base64 chars
    key_bytes = hashlib.sha256(settings.JWT_SECRET_KEY.encode()).digest()
    key_b64 = base64.urlsafe_b64encode(key_bytes)
    return Fernet(key_b64)


def encrypt_value(plain_text: str) -> str:
    """Encrypt a string value. Returns base64-encoded ciphertext."""
    if not plain_text:
        return ""
    f = _get_fernet()
    return f.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_value(cipher_text: str) -> str:
    """Decrypt a Fernet-encrypted string."""
    if not cipher_text:
        return ""
    f = _get_fernet()
    return f.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
