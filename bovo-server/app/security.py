"""Sécurité : hachage bcrypt + génération / validation JWT."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import jwt

from app.config import get_settings

_BCRYPT_COST = 12


def hash_password(plain: str) -> str:
    """Hache un mot de passe en clair avec bcrypt (coût 12)."""
    return bcrypt.hashpw(
        plain.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_COST),
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Vérifie qu'un mot de passe correspond à son hash bcrypt."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _now() -> datetime:
    return datetime.now(UTC)


def create_access_token(user_id: int, username: str, role: str) -> tuple[str, int]:
    """Génère un token d'accès JWT et retourne ``(token, expires_in_seconds)``."""
    settings = get_settings()
    expires_in = settings.access_token_minutes * 60
    payload: dict[str, Any] = {
        "sub": str(user_id), "username": username, "role": role,
        "type": "access",
        "exp": _now() + timedelta(minutes=settings.access_token_minutes),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, expires_in


def create_refresh_token(user_id: int) -> str:
    """Génère un token de rafraîchissement JWT (durée : ``refresh_token_days``)."""
    settings = get_settings()
    payload = {
        "sub": str(user_id), "type": "refresh",
        "exp": _now() + timedelta(days=settings.refresh_token_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Décode et valide un JWT. Lève ``jwt.PyJWTError`` en cas d'échec."""
    settings = get_settings()
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
