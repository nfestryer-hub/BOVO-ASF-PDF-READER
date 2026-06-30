"""Point d'entrée de BOVO Planning Manager.

Lance le splash screen animé puis la fenêtre principale. Configure la
journalisation, initialise la base SQLite et les paramètres, et garantit une
fermeture propre.

Exécution::

    python main.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import customtkinter as ctk

from app.database import Database
from app.gui import BovoApp, SplashScreen
from app.logger import LogAction, configure_logging, log_action
from app.settings import Settings
from app.utils import (
    ASSETS_DIR,
    DATABASE_DIR,
    EXPORT_DIR,
    LOGS_DIR,
    ensure_directories,
)


def main() -> int:
    """Initialise et exécute l'application. Retourne un code de sortie."""
    ensure_directories(DATABASE_DIR, ASSETS_DIR, LOGS_DIR, EXPORT_DIR)
    logger = configure_logging(LOGS_DIR, level=logging.INFO)
    logger.info("Démarrage de BOVO Planning Manager.")

    database = Database(DATABASE_DIR / "bovo.db")
    settings = Settings(database)
    log_action(database, LogAction.OPEN, "Ouverture de l'application.")

    ctk.set_appearance_mode(settings.theme)
    ctk.set_default_color_theme(settings.color_theme)

    app = BovoApp(database, settings)
    app.protocol("WM_DELETE_WINDOW", app.on_close)

    SplashScreen(app, on_finish=app.reveal)

    try:
        app.mainloop()
    except KeyboardInterrupt:  # pragma: no cover - arrêt manuel.
        logger.info("Interruption clavier : fermeture.")
        app.on_close()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
