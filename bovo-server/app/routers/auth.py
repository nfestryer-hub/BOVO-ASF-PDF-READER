"""Router : authentification (login, refresh, me)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import LoginAttempt, User
from app.schemas import (
    AccessTokenResponse, LoginRequest, RefreshRequest, TokenResponse, UserOut,
)
from app.security import (
    create_access_token, create_refresh_token, decode_token, verify_password,
)
from app.config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

_MAX_FAILED = 5
_LOCK_MINUTES = 15


def _brute_force_locked(db: Session, identifier: str) -> bool:
    """Retourne ``True`` si l'identifiant a dépassé les tentatives autorisées."""
    since = datetime.now(UTC) - timedelta(minutes=_LOCK_MINUTES)
    recent = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.identifier == identifier)
        .filter(LoginAttempt.created_at >= since)
        .filter(LoginAttempt.successful.is_(False))
        .count()
    )
    return recent >= _MAX_FAILED


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    """Authentifie un utilisateur et retourne un couple access + refresh."""
    username = payload.username.strip()
    identifier = username.lower()
    if _brute_force_locked(db, identifier):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives. Réessayez dans 15 minutes.",
        )
    user = db.scalar(select(User).where(User.username == username))
    ok = user is not None and user.is_active and verify_password(
        payload.password, user.password_hash,
    )
    db.add(LoginAttempt(identifier=identifier, successful=bool(ok)))
    db.commit()
    if not ok or user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Nom d'utilisateur ou mot de passe incorrect.",
        )
    user.last_login = datetime.now(UTC)
    db.commit()
    access, expires_in = create_access_token(user.id, user.username, user.role.value)
    refresh = create_refresh_token(user.id)
    return TokenResponse(
        access_token=access, refresh_token=refresh,
        expires_in=expires_in, user=UserOut.model_validate(user),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(
    payload: RefreshRequest,
    db: Annotated[Session, Depends(get_db)],
) -> AccessTokenResponse:
    """Émet un nouveau token d'accès à partir d'un refresh token valide."""
    try:
        data = decode_token(payload.refresh_token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token invalide.",
        ) from exc
    if data.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Type de token invalide.",
        )
    user = db.get(User, int(data.get("sub", 0)))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Utilisateur introuvable.",
        )
    access, expires_in = create_access_token(user.id, user.username, user.role.value)
    return AccessTokenResponse(access_token=access, expires_in=expires_in)


@router.get("/me", response_model=UserOut)
def me(user: Annotated[User, Depends(get_current_user)]) -> UserOut:
    """Retourne l'utilisateur courant à partir du token d'accès."""
    return UserOut.model_validate(user)


@router.get("/config")
def config() -> dict[str, int]:
    """Expose la configuration publique nécessaire aux clients (durées TTL)."""
    settings = get_settings()
    return {
        "access_token_minutes": settings.access_token_minutes,
        "refresh_token_days": settings.refresh_token_days,
    }
