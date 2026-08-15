"""JWT access-token creation and verification (PyJWT).

Tokens are deliberately narrow:

* signed with a symmetric algorithm from an allowlist (``config.ALLOWED_JWT_ALGORITHMS``),
  and verified against that single algorithm — never the one advertised in the
  token header, which is attacker-controlled;
* bound to an issuer and audience, so a token minted for another service (or
  another deployment sharing a secret) is not accepted here;
* carrying a ``typ`` marker, so a future refresh/reset token can never be
  replayed as an access token;
* carrying a unique ``jti``, which gives revocation lists and audit trails a
  handle to work with.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from ...config import get_settings

#: Marks a token as usable for API authentication.
ACCESS_TOKEN_TYPE = "access"

#: Claims that must be present and valid for a token to be accepted.
_REQUIRED_CLAIMS = ["exp", "iat", "nbf", "sub", "role", "jti", "typ"]


class TokenError(Exception):
    """Raised when a token is invalid, expired or malformed."""


def create_access_token(
    subject: str,
    *,
    role: str,
    expires_delta: timedelta | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT for *subject* (typically the user id)."""
    settings = get_settings()
    now = datetime.now(UTC)
    ttl = expires_delta or timedelta(minutes=settings.access_token_ttl_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "role": role,
        "typ": ACCESS_TOKEN_TYPE,
        "jti": secrets.token_urlsafe(16),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    if extra_claims:
        # Registered claims are set by this function alone; callers may only add
        # their own application claims on top.
        payload.update({k: v for k, v in extra_claims.items() if k not in payload})
    return jwt.encode(
        payload,
        settings.secret_key.get_secret_value(),
        algorithm=settings.algorithm,
    )


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT, returning its claims.

    Raises:
        TokenError: if the token is expired, tampered with, issued for a
            different audience/issuer, or is not an access token.
    """
    settings = get_settings()
    try:
        claims: dict[str, Any] = jwt.decode(
            token,
            settings.secret_key.get_secret_value(),
            algorithms=[settings.algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": _REQUIRED_CLAIMS},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        # Covers bad signature, wrong audience/issuer, missing claims and
        # malformed input. The message stays generic on purpose.
        raise TokenError("Invalid authentication token.") from exc

    if claims.get("typ") != ACCESS_TOKEN_TYPE:
        raise TokenError("Invalid authentication token.")
    return claims
