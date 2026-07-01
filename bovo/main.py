"""Point d'entrée de Bovo ASF Manager (mode client / serveur REST).

Séquence de démarrage :

1. Splash animé (logo BOVO).
2. **Configuration serveur** (si absente) → :class:`ServerConfigDialog`.
3. **Auto-login silencieux** via le refresh token JWT persisté, si présent.
4. Sinon :class:`LoginDialog` qui appelle ``client.login()``.
5. Démarrage du listener SSE en arrière-plan pour les mises à jour temps-réel.
6. Ouverture de la fenêtre principale filtrée selon le rôle utilisateur.

L'authentification est **exclusivement** effectuée via le backend FastAPI
(``POST /api/auth/login``). Aucune donnée d'authentification n'est stockée
en local. Seuls les préférences (thème, URL serveur, refresh token pour
l'auto-login) restent dans SQLite locale.

Exécution::

    python main.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import customtkinter as ctk

from app.api_client import ApiClient, ApiError
from app.database import Database
from app.gui import BovoApp, LoginDialog, SplashScreen
from app.logger import LogAction, configure_logging, log_action
from app.remote_services import AutoLoginNetworkError, RemoteAuditService, RemoteAuthService
from app.server_config_dialog import ServerConfigDialog
from app.session import Session
from app.settings import Settings
from app.sync import SseListener
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
    logger.info("Démarrage de Bovo ASF Manager (client REST).")

    # SQLite locale : SEULEMENT pour les préférences (Settings) et le journal
    # d'activité local (ouverture PDF, exports). Aucune donnée métier.
    database = Database(DATABASE_DIR / "bovo.db")
    settings = Settings(database)
    log_action(database, LogAction.OPEN, "Ouverture de l'application.")

    ctk.set_appearance_mode(settings.theme)
    ctk.set_default_color_theme(settings.color_theme)

    # ------------------------------------------------------------------ #
    # Instance UNIQUE d'ApiClient partagée par toute l'application.
    # ------------------------------------------------------------------ #
    client = ApiClient(base_url=settings.server_url or "http://localhost:8000")
    session = Session(client=client)
    auth = RemoteAuthService(client, session)
    audit = RemoteAuditService(client)
    sse_listener: SseListener | None = None

    app = BovoApp(database, settings, auth=auth, audit=audit)
    app.protocol("WM_DELETE_WINDOW", lambda: _shutdown(app, sse_listener, database))

    def _after_login() -> None:
        """Callback exécuté quand la connexion est validée."""
        nonlocal sse_listener
        current = auth.current_user
        if current is not None:
            audit.bind_session(current.username, current.role)
            logger.info("Authentifié comme %s (%s).", current.username, current.role)
        # Démarre le listener SSE pour la synchro temps-réel (Ctrl+F5 auto).
        sse_listener = SseListener(client, _on_sync_event)
        sse_listener.start()
        app.on_authenticated()

    def _on_sync_event(payload: dict) -> None:
        """Callback invoqué par le thread SSE ; marshal vers Tk main."""
        try:
            app.after(0, app._on_remote_event, payload)  # noqa: SLF001
        except Exception:  # noqa: BLE001 — GUI détruite après logout
            pass

    def _launch_login() -> None:
        """Ouvre l'écran de connexion (ou tente un auto-login)."""
        # 1. Tentative de reconnexion silencieuse via le refresh token JWT.
        remembered = settings.remembered_refresh_token
        if remembered:
            logger.info(
                "Auto-login : tentative avec un refresh token persisté (user=%r).",
                settings.remembered_username,
            )
            try:
                user = auth.try_auto_login(remembered)
            except AutoLoginNetworkError as exc:
                # Serveur/net indispo → on garde le token, on retombe sur le
                # login manuel avec le nom pré-rempli.
                logger.warning(
                    "Auto-login : serveur injoignable (%s). Token conservé.", exc,
                )
                user = None
            else:
                if user is not None:
                    logger.info("Auto-login réussi (user=%s).", user.username)
                    _after_login()
                    return
                # Refresh token vraiment expiré → purge (401/403).
                logger.info("Auto-login : token expiré/invalide — purge locale.")
                settings.forget()
        # 2. Écran de connexion classique.
        LoginDialog(
            app, auth,
            on_success=_after_login,
            on_cancel=lambda: _shutdown(app, sse_listener, database),
            settings=settings,
        )

    def _show_server_config() -> None:
        """Affiche la configuration serveur (obligatoire au 1er lancement)."""
        def _after_config() -> None:
            client._base_url = settings.server_url.rstrip("/")  # noqa: SLF001
            _launch_login()

        ServerConfigDialog(
            app, settings,
            on_success=_after_config,
            on_cancel=lambda: _shutdown(app, sse_listener, database),
        )

    def _start_after_splash() -> None:
        """Enchaîne : config serveur (si vide) → login."""
        if not settings.server_url:
            _show_server_config()
        else:
            _launch_login()

    SplashScreen(app, on_finish=_start_after_splash)

    try:
        app.mainloop()
    except KeyboardInterrupt:  # pragma: no cover
        logger.info("Interruption clavier : fermeture.")
        _shutdown(app, sse_listener, database)
    return 0


def _shutdown(
    app: BovoApp, sse_listener: SseListener | None, database: Database,
) -> None:
    """Ferme proprement l'application (SSE + DB + fenêtre)."""
    if sse_listener is not None:
        try:
            sse_listener.stop()
        except Exception:  # noqa: BLE001
            pass
    try:
        app.on_close()
    except Exception:  # noqa: BLE001
        pass
    try:
        database.close()
    except Exception:  # noqa: BLE001
        pass


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    raise SystemExit(main())
