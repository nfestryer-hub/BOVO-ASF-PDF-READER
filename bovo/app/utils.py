"""Fonctions utilitaires transverses de Bovo ASF Manager.

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
import sys
import unicodedata
from datetime import date, datetime
from pathlib import Path

from app.logger import get_logger

logger = get_logger("utils")


def _is_frozen() -> bool:
    """Retourne True si l'app tourne depuis un exécutable PyInstaller.

    Détection standard : ``sys.frozen`` est positionné par PyInstaller (et
    la plupart des packagers Python — cx_Freeze, Nuitka…).
    """
    return bool(getattr(sys, "frozen", False))


def _user_data_root() -> Path:
    """Racine des données utilisateur (persistantes, écrite au run-time).

    * Mode « frozen » (Bovo.exe distribué sur un partage réseau ou installé) :
      on utilise ``%APPDATA%\\Bovo`` (Windows) ou ``~/.local/share/Bovo``
      (Linux/macOS) pour que les paramètres, journal, DB locale et exports
      soient persistés PAR UTILISATEUR — indépendamment de l'emplacement
      de l'exe. Sans ça, un exe partagé écrirait ses données dans
      ``%TEMP%\\_MEI...`` qui est effacé à chaque redémarrage.
    * Mode dev (``python main.py``) : dossier du projet, comme avant.
    """
    if _is_frozen():
        if platform.system() == "Windows":
            base = Path(os.environ.get("APPDATA", "")) if os.environ.get("APPDATA") else Path.home() / "AppData" / "Roaming"
            return base / "Bovo"
        # Linux/macOS (peu probable pour cette app mais robuste).
        return Path.home() / ".local" / "share" / "Bovo"
    return Path(__file__).resolve().parent.parent


def _bundle_root() -> Path:
    """Racine des ressources bundlées (assets read-only : logo, icônes).

    En mode frozen, PyInstaller expose ``sys._MEIPASS`` (chemin d'extraction
    temporaire). En mode dev, on retombe sur la racine du projet.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = _bundle_root()               # assets read-only (logo, icônes)
_USER_ROOT = _user_data_root()              # writable per-user
DATABASE_DIR = _USER_ROOT / "database"      # SQLite local (settings, journal)
ASSETS_DIR = PROJECT_ROOT / "assets"        # bundle
LOGS_DIR = _USER_ROOT / "logs"              # journal fichier
EXPORT_DIR = _USER_ROOT / "exports"         # PDF/Excel générés


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


def parse_pk_to_meters(value: str | None) -> float | None:
    """Convertit une valeur de PK (Point Kilométrique) en mètres.

    Formats reconnus :
        * ``"12+345"`` → 12 345 m (km + m)
        * ``"12,345"`` ou ``"12.345"`` → 12 345 m (km décimal)
        * ``"12"`` (< 1000) → 12 000 m (km entier)
        * ``"12345"`` (≥ 1000) → 12 345 m (déjà en mètres)
        * préfixes ``PR`` / ``PK`` supportés

    Returns:
        Valeur en mètres, ou ``None`` si la valeur est illisible.
    """
    if value is None:
        return None
    raw = str(value).strip().upper().replace(" ", "")
    if not raw:
        return None
    raw = re.sub(r"^(PR|PK)", "", raw)
    if not raw:
        return None
    match = re.match(r"^(-?\d+)\+(\d{1,3})$", raw)
    if match:
        return int(match.group(1)) * 1000.0 + int(match.group(2))
    try:
        numeric = float(raw.replace(",", "."))
    except ValueError:
        return None
    has_decimal = "." in raw or "," in raw
    if has_decimal or abs(numeric) < 1000:
        return numeric * 1000.0
    return numeric


def compute_ml_inspectes(pk_depart: str | None, pk_arrivee: str | None) -> str:
    """Calcule le linéaire (ML) entre deux PK. Retourne une chaîne d'entier.

    Retourne une chaîne vide si l'une des deux valeurs est illisible.
    """
    a = parse_pk_to_meters(pk_depart)
    b = parse_pk_to_meters(pk_arrivee)
    if a is None or b is None:
        return ""
    return f"{abs(b - a):.0f}"


def parse_time_to_hours(value: str | None) -> float | None:
    """Convertit une heure (``HH:MM``, ``HHhMM``, ``8h``, ``8,5``) en heures décimales.

    Returns:
        Heures depuis minuit (float), ou ``None`` si illisible.
    """
    if value is None:
        return None
    raw = str(value).strip().lower().replace(" ", "")
    if not raw:
        return None
    match = re.match(r"^(\d{1,2})[h:](\d{1,2})$", raw)
    if match:
        hours, minutes = int(match.group(1)), int(match.group(2))
        return hours + minutes / 60.0
    match = re.match(r"^(\d{1,2})h$", raw)
    if match:
        return float(match.group(1))
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def compute_heures_totales(heure_debut: str | None, heure_fin: str | None) -> str:
    """Calcule la durée entre deux heures. Gère le passage à minuit.

    Retourne une chaîne au format ``X.Y`` (1 décimale) ou vide si illisible.
    """
    start = parse_time_to_hours(heure_debut)
    end = parse_time_to_hours(heure_fin)
    if start is None or end is None:
        return ""
    delta = end - start
    if delta < 0:
        delta += 24.0
    return f"{delta:.2f}".rstrip("0").rstrip(".") or "0"
