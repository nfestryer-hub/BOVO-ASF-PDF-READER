"""Couche de base de données SQLAlchemy 2.0 + PostgreSQL."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from app.config import get_settings


class Base(DeclarativeBase):
    """Base déclarative SQLAlchemy pour tous les modèles."""


settings = get_settings()

engine = create_engine(
    settings.postgres_dsn,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine, autocommit=False, autoflush=False, expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Dépendance FastAPI : ouvre une session par requête et la ferme."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
