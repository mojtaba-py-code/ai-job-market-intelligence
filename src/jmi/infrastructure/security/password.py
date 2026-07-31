"""Password hashing using bcrypt.

bcrypt automatically salts each hash and is deliberately slow, which is what we
want for password storage. The 72-byte input limit of bcrypt is handled by
encoding to UTF-8 and letting bcrypt truncate; we additionally guard against
absurdly long inputs to avoid unnecessary work.
"""

from __future__ import annotations

import bcrypt

_MAX_PASSWORD_BYTES = 1024


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash of *password*."""
    if not password:
        raise ValueError("Password must not be empty.")
    raw = password.encode("utf-8")[:_MAX_PASSWORD_BYTES]
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Return whether *password* matches the stored bcrypt *hashed* value."""
    if not password or not hashed:
        return False
    try:
        return bcrypt.checkpw(
            password.encode("utf-8")[:_MAX_PASSWORD_BYTES], hashed.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False
