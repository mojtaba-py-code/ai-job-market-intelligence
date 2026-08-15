"""Authentication use-cases: registration and login."""

from __future__ import annotations

import secrets
from functools import lru_cache

from sqlalchemy.orm import Session

from ...domain.enums import UserRole
from ...exceptions import (
    AuthenticationError,
    ConflictError,
    RateLimitedError,
    ValidationError,
)
from ...infrastructure.db.models import User
from ...infrastructure.db.repositories import UserRepository
from ...infrastructure.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from .login_throttle import get_login_throttle

MIN_PASSWORD_LENGTH = 8


@lru_cache(maxsize=1)
def _decoy_hash() -> str:
    """A real bcrypt hash of a random value, used to equalise login timing.

    When the email is unknown there is no stored hash to check, and returning
    immediately makes "no such user" measurably faster than "wrong password" —
    which turns the login endpoint into a user-enumeration oracle. Verifying
    against this decoy burns the same bcrypt work factor instead.

    It must be a *valid* hash: ``bcrypt.checkpw`` rejects a malformed one
    immediately without hashing, which would defeat the entire purpose.
    Computed once per process, on first use, so import stays cheap.
    """
    return hash_password(secrets.token_urlsafe(32))


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    def register(self, *, email: str, password: str, role: UserRole = UserRole.viewer) -> User:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValidationError(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
            )
        if self.users.get_by_email(email):
            raise ConflictError("A user with this email already exists.")
        return self.users.create(email=email, hashed_password=hash_password(password), role=role)

    def authenticate(self, *, email: str, password: str) -> User:
        # Per-account, so guesses spread across many source addresses — each one
        # staying under the per-address rate limit — still run out of budget.
        throttle = get_login_throttle()
        if throttle.is_locked(email):
            raise RateLimitedError(
                "Too many failed sign-in attempts. Try again in "
                f"{throttle.retry_after(email)} seconds."
            )

        user = self.users.get_by_email(email)
        if user is None:
            # Spend the same work as a real check before failing (see _decoy_hash).
            verify_password(password, _decoy_hash())
            throttle.record_failure(email)
            raise AuthenticationError("Invalid email or password.")
        if not verify_password(password, user.hashed_password):
            throttle.record_failure(email)
            raise AuthenticationError("Invalid email or password.")
        if not user.is_active:
            # Checked only after the password is confirmed, so a disabled
            # account is not disclosed to someone who does not hold its password.
            raise AuthenticationError("Account is disabled.")

        # A correct password clears the history, so someone deliberately failing
        # logins against a victim cannot keep the real owner locked out.
        throttle.record_success(email)
        return user

    def issue_token(self, user: User) -> str:
        return create_access_token(str(user.id), role=user.role.value)

    def login(self, *, email: str, password: str) -> str:
        user = self.authenticate(email=email, password=password)
        return self.issue_token(user)
