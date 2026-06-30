"""Fonctions utilitaires transverses de BOVO Planning Manager.

Regroupe des helpers sans état : récupération du nom d'utilisateur système,
ouverture native de fichiers, normalisation de texte, garanties de répertoires,
formatage de dates. Aucune dépendance vers la couche métier.
"""

from __future__ import annotations

import getpass
import os
import platform
import re
import subprocess
import unicodedata
from datetime import date, datetime
from pathlib import Path

from app.logger import get_logger

logger = get_logger("utils")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_DIR = PROJECT_ROOT / "database"
ASSETS_DIR = PROJECT_ROOT / "assets"
LOGS_DIR = PROJECT_ROOT / "logs"
EXPORT_DIR = PROJECT_ROOT / "exports"


def get_system_username() -> str:
    """Retourne le nom de l'utilisateur courant (Windows ou autre OS).

    Sur Windows, la variable ``USERNAME`` est privilégiée ; un repli multiple
    garantit qu'un nom non vide est toujours renvoyé.
    """
    for getter in (
        lambda: os.environ.get("USERNAME", ""),
        lambda: os.environ.get("USER", ""),
        getpass.getuser,
    ):
        try:
            name = getter()
        except Exception:  # noqa: BLE001 - on tente le getter suivant.
            name = ""
        if name:
            return name.strip().capitalize()
    return "Utilisateur"


def ensure_directories(*paths: Path) -> None:
    """Crée les répertoires fournis s'ils n'existent pas déjà."""
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)


def open_file_native(file_path: Path) -> bool:
    """Ouvre un fichier avec l'application par défaut du système.

    Args:
        file_path: Chemin du fichier à ouvrir.

    Returns:
        ``True`` si la commande d'ouverture a été lancée, ``False`` sinon.
    """
    if not file_path.exists():
        logger.warning("Fichier introuvable, ouverture impossible : %s", file_path)
        return False
    try:
        system = platform.system()
        if system == "Windows":
            os.startfile(str(file_path))  # type: ignore[attr-defined]  # noqa: SLF001
        elif system == "Darwin":
            subprocess.run(["open", str(file_path)], check=False)
        else:
            subprocess.run(["xdg-open", str(file_path)], check=False)
        return True
    except Exception as exc:  # noqa: BLE001 - ouverture best-effort.
        logger.error("Échec d'ouverture du fichier %s : %s", file_path, exc)
        return False


def normalize_text(value: str) -> str:
    """Normalise un texte : suppression des accents, casse et espaces réduits."""
    if not value:
        return ""
    stripped = unicodedata.normalize("NFKD", value)
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip().lower()


def slugify(value: str) -> str:
    """Transforme un texte en identifiant sûr pour un nom de fichier."""
    normalized = normalize_text(value)
    return re.sub(r"[^a-z0-9]+", "_", normalized).strip("_") or "bovo"


def format_date_fr(value: date | datetime | None) -> str:
    """Formate une date au format français ``JJ/MM/AAAA``."""
    if value is None:
        return ""
    return value.strftime("%d/%m/%Y")


def parse_iso_date(value: str | None) -> date | None:
    """Convertit une chaîne ISO (``AAAA-MM-JJ`` ou ISO datetime) en ``date``."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def human_readable_size(num_bytes: int) -> str:
    """Retourne une taille de fichier lisible (octets → Ko/Mo/Go)."""
    size = float(num_bytes)
    for unit in ("o", "Ko", "Mo", "Go", "To"):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} Po"
