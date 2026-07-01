"""Fenêtre de configuration de l'URL du serveur Bovo ASF Manager.

Affichée au premier lancement (ou depuis les Paramètres) pour saisir
l'adresse du backend FastAPI. Un bouton « Tester la connexion » appelle
``GET /api/health`` pour valider l'URL avant enregistrement.
"""

from __future__ import annotations

from collections.abc import Callable

import customtkinter as ctk
from PIL import Image

from app import __author__, __version__
from app.api_client import ApiClient, ApiError
from app.settings import Settings
from app.utils import ASSETS_DIR

ACCENT = "#E63946"
ACCENT_HOVER = "#B31E2F"
SURFACE = "#141519"


class ServerConfigDialog(ctk.CTkToplevel):
    """Écran de configuration de l'URL du serveur.

    Args:
        master: Fenêtre parente.
        settings: Objet :class:`Settings` où l'URL sera persistée.
        on_success: Callback exécuté après validation + enregistrement.
        on_cancel: Callback exécuté si l'utilisateur ferme la fenêtre sans
            avoir configuré d'URL.
    """

    def __init__(
        self,
        master: ctk.CTk,
        settings: Settings,
        on_success: Callable[[], None],
        on_cancel: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self._settings = settings
        self._on_success = on_success
        self._on_cancel = on_cancel

        self.title("Bovo ASF Manager — Configuration du serveur")
        self.geometry("500x520")
        self.resizable(False, False)
        self.configure(fg_color=SURFACE)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(50, self._center)
        self.grab_set()

        header = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0, height=150)
        header.pack(fill="x")
        header.pack_propagate(False)
        logo_path = ASSETS_DIR / "logo.png"
        if logo_path.exists():
            image = ctk.CTkImage(Image.open(logo_path), size=(88, 88))
            ctk.CTkLabel(header, image=image, text="").pack(pady=(14, 0))
        ctk.CTkLabel(
            header, text="Configuration du serveur", text_color="white",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).pack(pady=(6, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=32, pady=(20, 12))

        ctk.CTkLabel(
            body,
            text=("Saisissez l'adresse du backend fourni par votre "
                  "administrateur BOVO."),
            wraplength=420, justify="left", text_color="#B7B8BE",
            font=ctk.CTkFont(size=12),
        ).pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            body, text="URL du serveur", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(fill="x", pady=(0, 4))
        self._url_var = ctk.StringVar(value=settings.server_url)
        ctk.CTkEntry(
            body, textvariable=self._url_var, height=40,
            placeholder_text="http://192.168.1.42:8000",
        ).pack(fill="x", pady=(0, 12))

        ctk.CTkLabel(
            body,
            text=("💡  Exemples valides :\n"
                  "    • http://192.168.1.42:8000   (LAN BOVO)\n"
                  "    • https://bovo.entreprise.fr  (VPS avec TLS)"),
            justify="left", text_color="#7A7A80",
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", pady=(0, 12))

        self._status_label = ctk.CTkLabel(
            body, text="", font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._status_label.pack(fill="x", pady=(4, 4))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=32, pady=(0, 16))
        ctk.CTkButton(
            actions, text="🔌  Tester la connexion", height=40,
            fg_color="#457B9D", hover_color="#35617D",
            command=self._test_connection,
        ).pack(fill="x", pady=(0, 8))
        ctk.CTkButton(
            actions, text="💾  Enregistrer et continuer", height=44,
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._save,
        ).pack(fill="x")

        ctk.CTkLabel(
            self, text=f"v{__version__} · Développé par {__author__}",
            font=ctk.CTkFont(size=10), text_color="#7A7A80",
        ).pack(pady=(0, 8))

        self.bind("<Return>", lambda _e: self._save())

    def _center(self) -> None:
        """Centre la fenêtre à l'écran."""
        self.update_idletasks()
        w, h = 500, 520
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _normalized_url(self) -> str:
        """Retourne l'URL saisie normalisée (sans slash final)."""
        return self._url_var.get().strip().rstrip("/")

    def _test_connection(self) -> bool:
        """Appelle ``GET /api/health`` et affiche le résultat."""
        url = self._normalized_url()
        if not url:
            self._status_label.configure(text="⚠️  URL requise.", text_color=ACCENT)
            return False
        self._status_label.configure(text="⏳  Test en cours…", text_color="#B7B8BE")
        self.update_idletasks()
        client = ApiClient(url, timeout=5.0)
        try:
            payload = client.health()
        except ApiError as exc:
            self._status_label.configure(
                text=f"❌  Erreur API : {exc.status_code} {exc.detail}",
                text_color=ACCENT,
            )
            return False
        except Exception as exc:  # noqa: BLE001 - réseau
            self._status_label.configure(
                text=f"❌  Injoignable : {type(exc).__name__}",
                text_color=ACCENT,
            )
            return False
        finally:
            client.close()
        version = payload.get("version", "?")
        self._status_label.configure(
            text=f"✅  Serveur OK — Bovo ASF Manager API v{version}",
            text_color="#43AA8B",
        )
        return True

    def _save(self) -> None:
        """Enregistre l'URL et poursuit vers l'écran de connexion."""
        url = self._normalized_url()
        if not url:
            self._status_label.configure(text="⚠️  URL requise.", text_color=ACCENT)
            return
        if not self._test_connection():
            return
        self._settings.server_url = url
        self.grab_release()
        self.destroy()
        self._on_success()

    def _cancel(self) -> None:
        """Ferme la fenêtre sans avoir configuré (annule le démarrage)."""
        self.grab_release()
        self.destroy()
        self._on_cancel()
