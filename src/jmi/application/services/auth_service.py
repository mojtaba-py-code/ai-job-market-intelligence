"""Authentication use-cases: registration and login."""

from __future__ import annotations

from sqlalchemy.orm import Session

from ...domain.enums import UserRole
from ...exceptions import AuthenticationError, ConflictError
from ...infrastructure.db.models import User
from ...infrastructure.db.repositories import UserRepository
from ...infrastructure.security import (
    create_access_token,
    hash_password,
    verify_password,
)


class AuthService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)

    def register(self, *, email: str, password: str, role: UserRole = UserRole.viewer) -> User:
        if self.users.get_by_email(email):
            raise ConflictError("A user with this email already exists.")
        if len(password) < 8:
            raise ConflictError("Password must be at least 8 characters long.")
        return self.users.create(email=email, hashed_password=hash_password(password), role=role)

    def authenticate(self, *, email: str, password: str) -> User:
        user = self.users.get_by_email(email)
        # Always run verify to reduce user-enumeration timing differences.
        placeholder = "$2b$12$0000000000000000000000000000000000000000000000000000"
        if user is None:
            verify_password(password, placeholder)
            raise AuthenticationError("Invalid email or password.")
        if not user.is_active:
            raise AuthenticationError("Account is disabled.")
        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password.")
        return user

    def issue_token(self, user: User) -> str:
        return create_access_token(str(user.id), role=user.role.value)

    def login(self, *, email: str, password: str) -> str:
        user = self.authenticate(email=email, password=password)
        return self.issue_token(user)
