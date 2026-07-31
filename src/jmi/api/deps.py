"""FastAPI dependencies: DB session, current user, role guard."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from ..domain.enums import UserRole
from ..exceptions import AuthenticationError, AuthorizationError
from ..infrastructure.db.models import User
from ..infrastructure.db.repositories import UserRepository
from ..infrastructure.db.session import get_sessionmaker
from ..infrastructure.security.tokens import TokenError, decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token", auto_error=False)


def get_db() -> Iterator[Session]:
    """Yield a request-scoped SQLAlchemy session."""
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: Session = Depends(get_db),
) -> User:
    """Resolve the authenticated user from the bearer token."""
    if not token:
        raise AuthenticationError("Not authenticated.")
    try:
        claims = decode_access_token(token)
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    user_id = claims.get("sub")
    user = UserRepository(session).get(int(user_id)) if user_id else None
    if user is None or not user.is_active:
        raise AuthenticationError("User not found or inactive.")
    return user


def require_role(*allowed: UserRole) -> Callable[..., User]:
    """Dependency factory enforcing that the user has one of *allowed* roles."""

    def _guard(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed and user.role is not UserRole.admin:
            raise AuthorizationError("Insufficient permissions for this operation.")
        return user

    return _guard


def client_identifier(request: Request) -> str:
    """Best-effort client id for rate limiting (proxy-aware)."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "anonymous"
