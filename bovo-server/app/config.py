"""Configuration de Bovo ASF Manager Server.

Charge la configuration depuis les variables d'environnement (fichier
``.env`` en local, variables du conteneur en production). Les valeurs sont
strictement requises — aucune valeur par défaut sensible n'est fournie afin
que toute mauvaise configuration se voie immédiatement.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuration typée du service."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore",
    )

    # -- Base de données ------------------------------------------------- #
    postgres_dsn: str = Field(
        ..., description="URL de connexion PostgreSQL (postgresql+psycopg://…).",
    )

    # -- Sécurité -------------------------------------------------------- #
    jwt_secret: str = Field(..., min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 8         # 8 h — session de travail
    refresh_token_days: int = 30               # 30 j — reconnexion silencieuse

    # -- Admin seed idempotent ------------------------------------------ #
    admin_username: str = "Bovo"
    admin_password: str = Field(..., min_length=6)

    # -- CORS ------------------------------------------------------------ #
    allowed_origins: str = "*"

    # -- Environnement --------------------------------------------------- #
    environment: str = "production"


@lru_cache
def get_settings() -> Settings:
    """Retourne la configuration mise en cache pour la durée du process."""
    return Settings()  # type: ignore[call-arg]
