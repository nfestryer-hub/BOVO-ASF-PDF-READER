"""Seed idempotent de l'utilisateur Admin par défaut."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Role, User
from app.security import hash_password, verify_password

logger = logging.getLogger("bovo.seed")


def seed_admin(db: Session) -> None:
    """Crée l'utilisateur Admin ou met à jour son mot de passe si obsolète.

    * Si l'utilisateur n'existe pas → il est créé.
    * S'il existe mais que le mot de passe ne correspond plus au ``.env`` →
      le hash est actualisé.
    """
    settings = get_settings()
    existing = db.query(User).filter(User.username == settings.admin_username).first()
    if existing is None:
        db.add(User(
            username=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
            role=Role.ADMIN, full_name="Administrateur BOVO",
        ))
        db.commit()
        logger.info("Admin seed : utilisateur créé (%s).", settings.admin_username)
        return
    if not verify_password(settings.admin_password, existing.password_hash):
        existing.password_hash = hash_password(settings.admin_password)
        db.commit()
        logger.info("Admin seed : mot de passe mis à jour.")
