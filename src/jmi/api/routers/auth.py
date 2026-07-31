"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from ...application.services import AuthService
from ..deps import get_current_user, get_db
from ..schemas import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=201)
def register(payload: RegisterRequest, session: Session = Depends(get_db)) -> UserResponse:
    # Public registration always creates a 'viewer'; no role escalation possible.
    user = AuthService(session).register(email=payload.email, password=payload.password)
    return UserResponse(id=user.id, email=user.email, role=user.role, is_active=user.is_active)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_db)) -> TokenResponse:
    token = AuthService(session).login(email=payload.email, password=payload.password)
    return TokenResponse(access_token=token)


@router.post("/token", response_model=TokenResponse)
def token(
    form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_db)
) -> TokenResponse:
    """OAuth2 password-flow endpoint (used by the Swagger 'Authorize' button)."""
    access = AuthService(session).login(email=form.username, password=form.password)
    return TokenResponse(access_token=access)


@router.get("/me", response_model=UserResponse)
def me(user=Depends(get_current_user)) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, role=user.role, is_active=user.is_active)
