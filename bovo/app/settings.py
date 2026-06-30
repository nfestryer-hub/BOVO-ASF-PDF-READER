"""Gestion des paramètres applicatifs de BOVO Planning Manager.

Les paramètres sont persistés dans la table ``settings`` de SQLite. Cette
classe expose des accès typés (thème, dernier dossier, dimensions de fenêtre,
dossiers PDF/Export, sauvegarde automatique) avec des valeurs par défaut.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.database import Database
from app.logger import get_logger
from app.utils import EXPORT_DIR, PROJECT_ROOT

logger = get_logger("settings")

_DEFAULTS: dict[str, Any] = {
    "theme": "dark",
    "color_theme": "blue",
    "last_folder": str(PROJECT_ROOT),
    "window_width": 1280,
    "window_height": 800,
    "pdf_folder": str(PROJECT_ROOT / "sample"),
    "export_folder": str(EXPORT_DIR),
    "auto_save": True,
}


class Settings:
    """Façade typée au-dessus de la table ``settings``."""

    def __init__(self, database: Database) -> None:
        """Charge les paramètres existants et applique les valeurs par défaut."""
        self._db = database
        self._cache: dict[str, Any] = dict(_DEFAULTS)
        self._load()

    def _load(self) -> None:
        """Recharge le cache depuis la base, en complétant les manques."""
        for key, default in _DEFAULTS.items():
            stored = self._db.get_setting(key)
            if stored is None:
                self._db.set_setting(key, json.dumps(default))
                self._cache[key] = default
            else:
                try:
                    self._cache[key] = json.loads(stored)
                except json.JSONDecodeError:
                    self._cache[key] = stored

    def get(self, key: str, default: Any = None) -> Any:
        """Retourne la valeur d'un paramètre."""
        return self._cache.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Définit et persiste un paramètre."""
        self._cache[key] = value
        self._db.set_setting(key, json.dumps(value))
        logger.debug("Paramètre mis à jour : %s = %s", key, value)

    @property
    def theme(self) -> str:
        """Thème d'apparence (``dark`` / ``light`` / ``system``)."""
        return str(self._cache["theme"])

    @property
    def color_theme(self) -> str:
        """Thème de couleur CustomTkinter."""
        return str(self._cache["color_theme"])

    @property
    def window_size(self) -> tuple[int, int]:
        """Dimensions enregistrées de la fenêtre principale."""
        return int(self._cache["window_width"]), int(self._cache["window_height"])

    @property
    def pdf_folder(self) -> Path:
        """Dossier par défaut des PDF à importer."""
        return Path(str(self._cache["pdf_folder"]))

    @property
    def export_folder(self) -> Path:
        """Dossier par défaut des exports."""
        return Path(str(self._cache["export_folder"]))

    @property
    def auto_save(self) -> bool:
        """Indique si la sauvegarde automatique est active."""
        return bool(self._cache["auto_save"])
