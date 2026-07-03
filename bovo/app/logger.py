"""Système de journalisation centralisé de Bovo ASF Manager.

Ce module fournit :
    * un logger applicatif configuré (console + fichier rotatif léger) ;
    * une fonction :func:`log_action` qui enregistre les actions métier dans la
      table ``logs`` de la base SQLite (import, création, modification,
      suppression, erreurs, ouverture, fermeture, sauvegarde).

Aucune logique métier n'est présente ici : uniquement de l'infrastructure.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import StrEnum
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import uniquement pour le typage
    from app.database import Database

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class LogLevel(StrEnum):
    """Niveaux de journalisation métier stockés en base."""

    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"


class LogAction(StrEnum):
    """Catégories d'actions métier traçées dans le journal."""

    IMPORT = "IMPORT"
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    OPEN = "OPEN"
    CLOSE = "CLOSE"
    SAVE = "SAVE"
    EXPORT = "EXPORT"
    ERROR = "ERROR"


def configure_logging(log_dir: Path, level: int = logging.INFO) -> logging.Logger:
    """Configure et retourne le logger racine de l'application.

    Args:
        log_dir: Répertoire où écrire le fichier de log.
        level: Niveau de verbosité minimal.

    Returns:
        Le logger applicatif nommé ``bovo``.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("bovo")
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:  # Déjà configuré : on évite les doublons de handlers.
        return logger

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        log_dir / "bovo.log",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "bovo") -> logging.Logger:
    """Retourne un logger enfant du logger applicatif."""
    if name == "bovo":
        return logging.getLogger("bovo")
    return logging.getLogger(f"bovo.{name}")


def log_action(
    database: Database | None,
    action: LogAction,
    message: str,
    *,
    level: LogLevel = LogLevel.INFO,
) -> None:
    """Journalise une action métier (fichier + base SQLite si disponible).

    Args:
        database: Instance de base de données, ou ``None`` (log fichier seul).
        action: Catégorie d'action.
        message: Message lisible décrivant l'action.
        level: Niveau de gravité métier.
    """
    logger = get_logger("action")
    text = f"[{action.value}] {message}"
    if level is LogLevel.ERROR:
        logger.error(text)
    elif level is LogLevel.WARNING:
        logger.warning(text)
    else:
        logger.info(text)

    if database is None:
        return
    try:
        database.add_log(
            action=action.value,
            level=level.value,
            message=message,
            created_at=datetime.now(UTC).isoformat(),
        )
    except Exception as exc:  # noqa: BLE001 - le log ne doit jamais casser l'app.
        logger.error("Impossible d'écrire le log en base : %s", exc)
