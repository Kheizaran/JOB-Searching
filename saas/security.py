"""Passwords, sessions and key storage.

Two secrets matter here: the user's password, which we never store, and their
Anthropic API key, which we do store and therefore encrypt. If SAAS_SECRET_KEY
leaks, every stored key is exposed — treat it accordingly.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet, InvalidToken

SESSION_DAYS = 14
SCRYPT = dict(n=2**14, r=8, p=1, dklen=32)


def _secret() -> bytes:
    key = os.environ.get("SAAS_SECRET_KEY")
    if not key:
        raise RuntimeError(
            "SAAS_SECRET_KEY is not set. Generate one with:\n"
            "  python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
    return key.encode()


def _fernet() -> Fernet:
    digest = hashlib.sha256(_secret()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


# ---------- passwords ----------

def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("Use at least 10 characters.")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_hex, dk_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        dk = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **SCRYPT)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


# ---------- api keys ----------

def encrypt_key(api_key: str) -> str:
    return _fernet().encrypt(api_key.strip().encode()).decode()


def decrypt_key(blob: str | None) -> str | None:
    if not blob:
        return None
    try:
        return _fernet().decrypt(blob.encode()).decode()
    except InvalidToken:
        return None


def key_hint(api_key: str) -> str:
    """What we show back: enough to recognise, not enough to use."""
    return f"{api_key[:11]}…{api_key[-4:]}" if len(api_key) > 18 else "set"


# ---------- sessions ----------

def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat(timespec="seconds")


def session_alive(expires_at: str) -> bool:
    try:
        return datetime.fromisoformat(expires_at) > datetime.now(timezone.utc)
    except ValueError:
        return False
