"""Configuration locale persistée en JSON dans le dossier utilisateur.

Sur Windows, les tokens et l'URL du serveur peuvent être perdus si la base
SQLite locale (``database/bovo.db``) est écrasée par une réinstallation ou
supprimée par un utilisateur. Ce module fournit un stockage **secondaire**
en JSON dans le dossier utilisateur (``%APPDATA%/BovoASF`` sur Windows,
``~/.config/BovoASF`` sur Linux/macOS) qui survit à ces événements.

Le fichier stocke uniquement des données non sensibles côté machine (URL du
serveur, nom d'utilisateur, refresh token JWT signé par le serveur). Il
n'est pas chiffré — la sécurité repose sur les permissions du dossier
utilisateur et sur la révocation côté serveur.

Le module est utilisé conjointement avec :class:`app.settings.Settings` :
lorsque la valeur SQLite est vide, le module tente un fallback JSON. Toute
écriture est répliquée dans les deux stockages.
"""

from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Any

from app.logger import get_logger

logger = get_logger("local_config")

_FILENAME = "bovo_config.json"


def _user_config_dir() -> Path:
    """Retourne le dossier utilisateur pour les données de config Bovo."""
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "BovoASF"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "BovoASF"
    xdg = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(xdg) / "BovoASF"


def config_path() -> Path:
    """Retourne le chemin absolu du fichier JSON de configuration locale."""
    return _user_config_dir() / _FILENAME


def load() -> dict[str, Any]:
    """Charge la configuration JSON. Retourne un dict vide si absent/illisible."""
    path = config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Impossible de lire %s : %s", path, exc)
        return {}


def save(data: dict[str, Any]) -> None:
    """Persiste la configuration JSON de manière atomique."""
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp, path)
    except OSError as exc:
        logger.warning("Impossible d'écrire %s : %s", path, exc)


def get(key: str, default: str = "") -> str:
    """Retourne la valeur d'une clé (chaîne). ``default`` si absente."""
    return str(load().get(key, default) or "")


def set_value(key: str, value: str) -> None:
    """Écrit ou met à jour une clé dans le fichier JSON."""
    data = load()
    if value:
        data[key] = value
    else:
        data.pop(key, None)
    save(data)


def clear(*keys: str) -> None:
    """Supprime les clés fournies (ou tout le fichier si aucune)."""
    if not keys:
        try:
            config_path().unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Impossible de supprimer %s : %s", config_path(), exc)
        return
    data = load()
    changed = False
    for key in keys:
        if key in data:
            data.pop(key, None)
            changed = True
    if changed:
        save(data)
