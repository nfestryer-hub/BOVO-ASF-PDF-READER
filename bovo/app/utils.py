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

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_DIR = PROJECT_ROOT / "database"
LOGS_DIR = PROJECT_ROOT / "logs"
EXPORT_DIR = PROJECT_ROOT / "exports"


def _executable_dir() -> Path:
    """Retourne le dossier de l'exécutable / du script principal.

    Sous PyInstaller (mode ``--onefile``), ``sys.executable`` pointe vers le
    binaire déballé côté utilisateur. En mode développement, on retourne la
    racine du projet.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def _bundle_dir() -> Path:
    """Retourne le dossier des ressources embarquées par PyInstaller.

    En mode ``--onefile``, PyInstaller extrait les données dans un dossier
    temporaire exposé via ``sys._MEIPASS``. En mode ``--onedir``, il s'agit
    du dossier ``_internal`` à côté du binaire.
    """
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return PROJECT_ROOT


def resource_path(*parts: str | Path) -> Path:
    """Retourne le chemin absolu d'une ressource (asset) — override friendly.

    Recherche dans l'ordre :

    1. **Dossier utilisateur** : ``<exe>/assets/<parts>`` — priorité maximale
       pour permettre à l'utilisateur de remplacer ``logo.png`` ou
       ``app.ico`` **sans recompiler** (il suffit de déposer le nouveau
       fichier à côté de l'exécutable).
    2. **Bundle PyInstaller** : ``<_MEIPASS>/assets/<parts>`` — la valeur
       par défaut embarquée dans l'exe.
    3. **Racine projet** : ``<project>/assets/<parts>`` — pour le mode dev.

    Le premier chemin existant est retourné. Si aucun n'existe, le premier
    chemin (utilisateur) est renvoyé quand même — le code appelant décidera
    du fallback (par ex. logo textuel).
    """
    candidates = [
        _executable_dir() / "assets" / Path(*parts),
        _bundle_dir() / "assets" / Path(*parts),
        PROJECT_ROOT / "assets" / Path(*parts),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


# ------------------------------------------------------------------ #
# Emplacements historiquement exposés — préservés pour compatibilité.
# ------------------------------------------------------------------ #

#: Dossier des ressources visuelles (icônes, logo, icône Windows).
#:
#: En mode installé (exe PyInstaller), pointe vers le dossier ``assets``
#: à côté du binaire — l'utilisateur peut y déposer sa propre version de
#: ``logo.png`` et ``app.ico`` sans recompiler. En mode développement,
#: pointe vers ``<projet>/assets``.
ASSETS_DIR = _executable_dir() / "assets"
if not ASSETS_DIR.exists():
    # Fallback : ressources embarquées par PyInstaller (--onefile).
    _bundled = _bundle_dir() / "assets"
    if _bundled.exists():
        ASSETS_DIR = _bundled
    else:
        ASSETS_DIR = PROJECT_ROOT / "assets"


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
