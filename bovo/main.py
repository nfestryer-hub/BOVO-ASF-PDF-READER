"""Point d'entrée de Bovo ASF Manager.

Séquence de démarrage :

1. Splash animé (logo BOVO + « Développé par HENRI Dylan »).
2. Écran de connexion (compte utilisateur local, bcrypt).
3. Ouverture de la fenêtre principale avec droits filtrés selon le rôle.

Configure la journalisation, initialise la base SQLite, seed les utilisateurs
par défaut, garantit une fermeture propre.

Exécution::

    python main.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import customtkinter as ctk

from app.audit import AuditService
from app.auth import AuthService
from app.database import Database
from app.gui import BovoApp, LoginDialog, SplashScreen
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
    logger.info("Démarrage de Bovo ASF Manager.")

    database = Database(DATABASE_DIR / "bovo.db")
    settings = Settings(database)
    auth = AuthService(database)
    audit = AuditService(database)
    log_action(database, LogAction.OPEN, "Ouverture de l'application.")

    ctk.set_appearance_mode(settings.theme)
    ctk.set_default_color_theme(settings.color_theme)

    app = BovoApp(database, settings, auth=auth, audit=audit)
    app.protocol("WM_DELETE_WINDOW", app.on_close)

    def _after_login() -> None:
        """Callback exécuté quand la connexion est validée."""
        current = auth.current_user
        if current is not None:
            audit.bind_session(current.username, current.role.value)
        app.on_authenticated()

    def _show_login() -> None:
        """Ouvre la fenêtre de connexion (bloquante)."""
        # Auto-login si l'utilisateur a coché « Se souvenir de moi » précédemment.
        if settings.remembered_username and settings.remembered_hash:
            user = auth.try_auto_login(
                settings.remembered_username, settings.remembered_hash
            )
            if user is not None:
                _after_login()
                return
            # Session obsolète : purge silencieuse.
            settings.forget()
        LoginDialog(
            app, auth, on_success=_after_login, on_cancel=app.on_close,
            settings=settings,
        )

    SplashScreen(app, on_finish=_show_login)

    try:
        app.mainloop()
    except KeyboardInterrupt:  # pragma: no cover - arrêt manuel.
        logger.info("Interruption clavier : fermeture.")
        app.on_close()
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
