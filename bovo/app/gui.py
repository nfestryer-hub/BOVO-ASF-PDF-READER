"""Interface graphique CustomTkinter de Bovo ASF Manager.

⚠️ Ce module ne contient AUCUNE logique métier : il se contente d'appeler les
services (``Planner``, ``Database``, ``Settings``, ``Exporter``) et d'afficher
les résultats. Toute la logique réside dans les autres modules du package.

Composants :
    * :class:`SplashScreen` — écran de démarrage animé (fondu + logo).
    * :class:`InterventionDialog` — fiche détaillée d'une intervention.
    * :class:`BovoApp` — fenêtre principale (accueil, calendrier, interventions,
      import, journal, paramètres).
"""

from __future__ import annotations

import queue
import threading
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Any

import customtkinter as ctk
from PIL import Image

from app import __author__, __version__
from app.audit import AuditEntry, AuditService
from app.auth import AuthService, Role, User
from app.calendar import STATUT_COLORS, WEEKDAY_NAMES_FR, CalendarModel, DayCell
from app.database import Database
from app.documents import Document
from app.exporter import Exporter
from app.inspections import FieldSpec
from app.remote_services import (
    ImportResult,
    RemoteDocumentService,
    RemoteInspectionService,
    RemotePlanner,
)
from app.logger import LogAction, get_logger, log_action
from app.models import Intervention, StatutIntervention
from app.settings import Settings
from app.utils import (
    ASSETS_DIR,
    compute_heures_totales,
    compute_ml_inspectes,
    format_date_fr,
    get_system_username,
    open_file_native,
    parse_iso_date,
)

logger = get_logger("gui")

ACCENT = "#E63946"
ACCENT_HOVER = "#C32A38"
CARD_BG = ("#F2F2F2", "#1B1B1F")
SURFACE = ("#FFFFFF", "#232329")


class LoginDialog(ctk.CTkToplevel):
    """Fenêtre de connexion (bcrypt local) — pré-requis avant l'application.

    L'utilisateur choisit son compte, saisit son mot de passe et se connecte.
    Un compteur d'erreurs consécutives verrouille temporairement le champ après
    5 tentatives ratées (protection basique contre les essais aveugles).
    """

    _MAX_FAILED = 5

    def __init__(
        self,
        master: ctk.CTk,
        auth: AuthService,
        on_success: Callable[[], None],
        on_cancel: Callable[[], None],
        settings: Settings | None = None,
    ) -> None:
        super().__init__(master)
        self._auth = auth
        self._settings = settings
        self._on_success = on_success
        self._on_cancel = on_cancel
        self._failed = 0

        self.title("Bovo ASF Manager — Connexion")
        self.geometry("440x640")
        self.resizable(False, False)
        self.configure(fg_color=SURFACE)
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.after(50, self._center)
        self.grab_set()

        header = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0, height=170)
        header.pack(fill="x")
        header.pack_propagate(False)
        logo_path = ASSETS_DIR / "logo.png"
        if logo_path.exists():
            image = ctk.CTkImage(Image.open(logo_path), size=(110, 110))
            ctk.CTkLabel(header, image=image, text="").pack(pady=(14, 0))
        ctk.CTkLabel(
            header, text="Connexion", text_color="white",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(pady=(6, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=32, pady=24)

        ctk.CTkLabel(
            body, text="Nom d'utilisateur", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(fill="x", pady=(0, 4))
        self._username_var = ctk.StringVar()
        self._username_entry = ctk.CTkEntry(
            body, textvariable=self._username_var, height=42,
            placeholder_text="Bovo / Dylan HENRI / ASF",
        )
        self._username_entry.pack(fill="x", pady=(0, 14))

        ctk.CTkLabel(
            body, text="Mot de passe", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(fill="x", pady=(0, 4))
        self._password_var = ctk.StringVar()
        self._password_entry = ctk.CTkEntry(
            body, textvariable=self._password_var, height=42,
            show="•", placeholder_text="Votre mot de passe",
        )
        self._password_entry.pack(fill="x", pady=(0, 8))

        self._show_pwd = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            body, text="Afficher le mot de passe", variable=self._show_pwd,
            command=self._toggle_password, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, checkbox_height=18, checkbox_width=18,
        ).pack(anchor="w", pady=(0, 6))

        self._remember_me = ctk.BooleanVar(
            value=bool(self._settings and self._settings.remembered_username)
        )
        ctk.CTkCheckBox(
            body, text="Se souvenir de moi sur cet appareil",
            variable=self._remember_me, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, checkbox_height=18, checkbox_width=18,
        ).pack(anchor="w", pady=(0, 4))
        ctk.CTkLabel(
            body,
            text="🔐  Votre session sera reconduite automatiquement pendant 30 jours.",
            font=ctk.CTkFont(size=10), text_color="#7A7A80", anchor="w",
        ).pack(anchor="w", pady=(0, 10))

        # Pré-remplissage du username si mémorisé.
        if self._settings and self._settings.remembered_username:
            self._username_var.set(self._settings.remembered_username)
            self.after(100, self._password_entry.focus_set)

        self._error_label = ctk.CTkLabel(
            body, text="", text_color=ACCENT,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self._error_label.pack(fill="x", pady=(0, 4))

        self._login_btn = ctk.CTkButton(
            body, text="Se connecter", height=46, fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._attempt_login,
        )
        self._login_btn.pack(fill="x", pady=(6, 0))

        ctk.CTkLabel(
            body, text=f"v{__version__} · Développé par {__author__}",
            font=ctk.CTkFont(size=10), text_color="#8A8A90",
        ).pack(side="bottom", pady=(20, 0))

        self.bind("<Return>", lambda _e: self._attempt_login())
        self.after(100, self._username_entry.focus_set)

    def _center(self) -> None:
        """Centre la fenêtre de connexion à l'écran."""
        self.update_idletasks()
        w, h = 440, 640
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _toggle_password(self) -> None:
        """Bascule l'affichage du mot de passe."""
        self._password_entry.configure(show="" if self._show_pwd.get() else "•")

    def _attempt_login(self) -> None:
        """Tente la connexion avec les identifiants saisis."""
        if self._failed >= self._MAX_FAILED:
            self._error_label.configure(
                text="Trop d'échecs. Fermez et relancez le logiciel."
            )
            return
        username = self._username_var.get().strip()
        password = self._password_var.get()
        if not username or not password:
            self._error_label.configure(text="Identifiants requis.")
            return
        user = self._auth.login(username, password)
        if user is None:
            self._failed += 1
            self._password_var.set("")
            remaining = self._MAX_FAILED - self._failed
            self._error_label.configure(
                text=f"Identifiants incorrects. {remaining} tentative(s) restante(s)."
            )
            return
        # Gestion « Se souvenir de moi » — stocke le refresh_token JWT.
        if self._settings is not None:
            checked = bool(self._remember_me.get())
            logger.info(
                "LoginDialog: connexion OK (user=%s) — remember_me=%s.",
                username, checked,
            )
            if checked:
                refresh_token = ""
                client = getattr(self._auth, "_client", None)
                if client is not None:
                    refresh_token = client.tokens.refresh_token or ""
                logger.info(
                    "LoginDialog: refresh_token %s (%d chars).",
                    "présent" if refresh_token else "absent",
                    len(refresh_token),
                )
                if refresh_token:
                    self._settings.remember(username, refresh_token)
                    # Vérification post-écriture : on relit depuis SQLite
                    # pour s'assurer que la persistance a bien fonctionné.
                    stored = self._settings.remembered_refresh_token
                    if stored != refresh_token:
                        logger.error(
                            "LoginDialog: persistance du refresh_token ÉCHOUÉE "
                            "(stored=%d chars, expected=%d).",
                            len(stored), len(refresh_token),
                        )
                    else:
                        logger.info(
                            "LoginDialog: refresh_token persisté avec succès.",
                        )
                else:
                    logger.warning(
                        "LoginDialog: refresh_token vide — rien à persister.",
                    )
            else:
                self._settings.forget()
        self._error_label.configure(text="")
        self.grab_release()
        self.destroy()
        self._on_success()

    def _cancel(self) -> None:
        """Ferme la fenêtre de connexion et l'application."""
        self.grab_release()
        self.destroy()
        self._on_cancel()


class SplashScreen(ctk.CTkToplevel):
    """Écran de démarrage avec logo BOVO et effet de fondu."""

    def __init__(self, master: ctk.CTk, on_finish: Callable[[], None]) -> None:
        super().__init__(master)
        self._on_finish = on_finish
        self.overrideredirect(True)
        self.configure(fg_color="#0D0D0F")
        width, height = 520, 360
        self._center(width, height)
        self.attributes("-alpha", 0.0)

        logo_path = ASSETS_DIR / "logo.png"
        if logo_path.exists():
            image = ctk.CTkImage(Image.open(logo_path), size=(240, 240))
            ctk.CTkLabel(self, image=image, text="").pack(pady=(40, 10))
        else:  # Repli textuel si le logo est absent.
            ctk.CTkLabel(
                self, text="BOVO", font=ctk.CTkFont(size=54, weight="bold"),
                text_color=ACCENT,
            ).pack(pady=(80, 10))

        ctk.CTkLabel(
            self, text="Bovo ASF Manager",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack()
        ctk.CTkLabel(
            self, text=f"Développé par {__author__}",
            font=ctk.CTkFont(size=13), text_color="#9A9AA0",
        ).pack(pady=(6, 0))

        self._alpha = 0.0
        self.after(50, self._fade_in)

    def _center(self, width: int, height: int) -> None:
        """Centre la fenêtre du splash sur l'écran."""
        x = (self.winfo_screenwidth() - width) // 2
        y = (self.winfo_screenheight() - height) // 2
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _fade_in(self) -> None:
        """Anime l'apparition progressive du splash."""
        self._alpha = min(self._alpha + 0.08, 1.0)
        self.attributes("-alpha", self._alpha)
        if self._alpha < 1.0:
            self.after(40, self._fade_in)
        else:
            self.after(1100, self._fade_out)

    def _fade_out(self) -> None:
        """Anime la disparition puis déclenche l'ouverture du logiciel."""
        self._alpha = max(self._alpha - 0.1, 0.0)
        self.attributes("-alpha", self._alpha)
        if self._alpha > 0.0:
            self.after(35, self._fade_out)
        else:
            self.destroy()
            self._on_finish()


class InterventionDialog(ctk.CTkToplevel):
    """Fiche détaillée d'une intervention avec bouton d'ouverture du PDF."""

    def __init__(
        self,
        master: ctk.CTk,
        intervention: Intervention,
        on_status_change: Callable[[Intervention, StatutIntervention], None],
    ) -> None:
        super().__init__(master)
        self._iv = intervention
        self._on_status_change = on_status_change
        self.title(f"Ouvrage {intervention.ouvrage}")
        self.geometry("520x620")
        self.configure(fg_color=SURFACE)
        self.grab_set()

        header = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(
            header, text=f"{intervention.objet}  ·  {intervention.ouvrage}",
            font=ctk.CTkFont(size=20, weight="bold"), text_color="white",
        ).pack(padx=20, pady=18, anchor="w")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=10)

        rows = [
            ("Ouvrage", intervention.ouvrage),
            ("Objet", intervention.objet),
            ("Autoroute", intervention.autoroute),
            ("Secteur", intervention.secteur or "—"),
            ("PR début", intervention.pr_debut or "—"),
            ("PR fin", intervention.pr_fin or "—"),
            ("Sens", intervention.sens or "—"),
            ("Longueur", intervention.longueur or "—"),
            ("Diamètre", intervention.diametre or "—"),
            ("Type d'ouvrage", intervention.type_ouvrage or "—"),
            ("Date début", format_date_fr(intervention.date_debut) or "—"),
            ("Date fin", format_date_fr(intervention.date_fin) or "—"),
            ("Statut", intervention.statut.value),
            ("Commentaire", intervention.commentaire or "—"),
        ]
        for label, value in rows:
            line = ctk.CTkFrame(body, fg_color="transparent")
            line.pack(fill="x", pady=4)
            ctk.CTkLabel(
                line, text=label, width=130, anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).pack(side="left")
            ctk.CTkLabel(
                line, text=value, anchor="w", justify="left", wraplength=320,
            ).pack(side="left", fill="x", expand=True)

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=20, pady=12)

        self._status_var = ctk.StringVar(value=intervention.statut.value)
        ctk.CTkLabel(controls, text="Changer le statut :").pack(side="left")
        ctk.CTkOptionMenu(
            controls,
            values=[s.value for s in StatutIntervention],
            variable=self._status_var,
            command=self._change_status,
            fg_color=ACCENT, button_color=ACCENT_HOVER,
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            self, text="📄  Ouvrir le PDF", fg_color=ACCENT,
            hover_color=ACCENT_HOVER, height=42,
            command=self._open_pdf,
        ).pack(fill="x", padx=20, pady=(0, 16))

    def _change_status(self, value: str) -> None:
        """Délègue le changement de statut au callback fourni."""
        statut = StatutIntervention.from_value(value)
        self._on_status_change(self._iv, statut)

    def _open_pdf(self) -> None:
        """Ouvre le PDF source de l'intervention dans l'application native."""
        if not self._iv.pdf_path or not open_file_native(Path(self._iv.pdf_path)):
            messagebox.showwarning("PDF", "Le PDF source est introuvable.")


class RowFormDialog(ctk.CTkToplevel):
    """Formulaire générique d'ajout/édition d'une ligne de module ASF."""

    def __init__(
        self,
        master: ctk.CTk,
        service: "RemoteInspectionService",
        sheet: str,
        row_id: int | None,
        on_saved: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self._service = service
        self._sheet = sheet
        self._row_id = row_id
        self._on_saved = on_saved
        self._widgets: dict[str, Any] = {}

        label = service.sheet_label(sheet)
        verb = "Modifier" if row_id is not None else "Ajouter"
        self.title(f"{verb} — {label}")
        # Formulaire ASF (rapports) : mise en page 4 sections, plus large.
        if sheet == "rapports":
            self.geometry("1180x780")
        else:
            self.geometry("560x680")
        self.configure(fg_color=SURFACE)
        self.grab_set()

        head = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0)
        head.pack(fill="x")
        title_text = f"{verb} une entrée — {label}"
        if sheet == "rapports":
            title_text = (
                f"{verb} un rapport d'inspection ASF "
                "— formulaire visites assainissement V2026-06-01"
            )
        ctk.CTkLabel(
            head, text=title_text,
            font=ctk.CTkFont(size=18, weight="bold"), text_color="white",
        ).pack(padx=20, pady=16, anchor="w")

        existing = service.get_row(sheet, row_id) if row_id is not None else {}
        if row_id is None and sheet == "rapports":
            existing = service.prefill_rapport()

        if sheet == "rapports":
            self._build_asf_sections(existing or {})
        else:
            body = ctk.CTkScrollableFrame(self, fg_color="transparent")
            body.pack(fill="both", expand=True, padx=20, pady=10)
            for field in service.form_fields(sheet):
                self._build_field(body, field, (existing or {}).get(field.column, ""))

        if sheet == "inspections":
            self._wire_inspections_autocalc()

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=12)
        ctk.CTkButton(
            actions, text="💾  Enregistrer", fg_color=ACCENT,
            hover_color=ACCENT_HOVER, height=42, command=self._save,
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            actions, text="Annuler", fg_color="transparent", border_width=1,
            text_color=("black", "white"), height=42, width=120,
            command=self.destroy,
        ).pack(side="left", padx=(10, 0))

    # ------------------------------------------------------------------ #
    # Mise en page ASF (rapports d'inspection)
    # ------------------------------------------------------------------ #
    def _build_asf_sections(self, existing: dict[str, str]) -> None:
        """Construit le formulaire rapport en 4 sections ASF horizontales.

        Chaque section est une carte verticale (Informations Générales,
        Caractéristiques de l'ouvrage, Surveillance générale, Autres
        documents). L'ensemble est encapsulé dans un ``CTkScrollableFrame``
        horizontal + vertical au cas où l'écran serait limité.
        """
        from app.inspections import ASF_RAPPORT_SECTIONS

        # Index rapide {column → FieldSpec} pour retrouver widget/référentiel.
        field_index: dict[str, FieldSpec] = {
            f.column: f for f in self._service.form_fields("rapports")
        }

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=16, pady=8)

        columns = ctk.CTkFrame(body, fg_color="transparent")
        columns.pack(fill="both", expand=True)
        # Une colonne par section, poids égal.
        for i in range(len(ASF_RAPPORT_SECTIONS)):
            columns.grid_columnconfigure(i, weight=1, uniform="asf")
        columns.grid_rowconfigure(0, weight=1)

        # Couleurs d'accent ASF pour chaque section (cohérence avec l'Excel).
        section_colors = ["#E63946", "#457B9D", "#F4A261", "#2A9D8F"]

        for idx, (section_title, fields) in enumerate(ASF_RAPPORT_SECTIONS):
            color = section_colors[idx % len(section_colors)]
            card = ctk.CTkFrame(columns, fg_color=CARD_BG, corner_radius=12)
            card.grid(row=0, column=idx, sticky="nsew", padx=6, pady=4)

            # En-tête de section coloré (comme les cellules fusionnées Excel).
            header = ctk.CTkFrame(card, fg_color=color, corner_radius=0, height=42)
            header.pack(fill="x")
            header.pack_propagate(False)
            ctk.CTkLabel(
                header, text=section_title, text_color="white",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).pack(padx=12, pady=10, anchor="w")

            content = ctk.CTkFrame(card, fg_color="transparent")
            content.pack(fill="both", expand=True, padx=12, pady=10)

            for column, label_text in fields:
                field_spec = field_index.get(column)
                if field_spec is None:
                    continue
                # Override du libellé pour matcher les intitulés ASF.
                labelled = FieldSpec(
                    column=field_spec.column,
                    label=label_text,
                    widget=field_spec.widget,
                    ref_key=field_spec.ref_key,
                )
                self._build_asf_field(content, labelled, existing.get(column, ""))

    def _build_asf_field(
        self, master: ctk.CTkBaseClass, field: FieldSpec, value: str,
    ) -> None:
        """Construit un champ ASF (label empilé au-dessus du widget, verticalement)."""
        wrapper = ctk.CTkFrame(master, fg_color="transparent")
        wrapper.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(
            wrapper, text=field.label, anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=("#333333", "#DDDDDD"),
        ).pack(fill="x", pady=(0, 2))

        if field.widget == "choice":
            options = ["—", *self._service.referentiel(field.ref_key)]
            var = ctk.StringVar(value=value if value in options else "—")
            ctk.CTkOptionMenu(
                wrapper, values=options, variable=var, height=32,
                fg_color=ACCENT, button_color=ACCENT_HOVER, dropdown_hover_color=ACCENT,
            ).pack(fill="x")
            self._widgets[field.column] = var
        elif field.widget == "long":
            box = ctk.CTkTextbox(wrapper, height=70)
            box.pack(fill="x")
            box.insert("1.0", value)
            self._widgets[field.column] = box
        else:
            display = value
            if field.widget == "date" and value:
                display = format_date_fr(parse_iso_date(value)) or value
            var = ctk.StringVar(value=display)
            placeholder = "JJ/MM/AAAA" if field.widget == "date" else ""
            ctk.CTkEntry(
                wrapper, textvariable=var, placeholder_text=placeholder,
                height=32,
            ).pack(fill="x")
            self._widgets[field.column] = var

    def _build_field(
        self, master: ctk.CTkBaseClass, field: FieldSpec, value: str
    ) -> None:
        """Construit le widget correspondant au type de champ."""
        line = ctk.CTkFrame(master, fg_color="transparent")
        line.pack(fill="x", pady=6)
        ctk.CTkLabel(
            line, text=field.label, width=170, anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).pack(side="left")

        if field.widget == "choice":
            options = ["—", *self._service.referentiel(field.ref_key)]
            var = ctk.StringVar(value=value if value in options else "—")
            ctk.CTkOptionMenu(
                line, values=options, variable=var,
                fg_color=ACCENT, button_color=ACCENT_HOVER,
            ).pack(side="left", fill="x", expand=True)
            self._widgets[field.column] = var
        elif field.widget == "long":
            box = ctk.CTkTextbox(line, height=60)
            box.pack(side="left", fill="x", expand=True)
            box.insert("1.0", value)
            self._widgets[field.column] = box
        else:
            display = value
            if field.widget == "date" and value:
                display = format_date_fr(parse_iso_date(value)) or value
            var = ctk.StringVar(value=display)
            placeholder = "JJ/MM/AAAA" if field.widget == "date" else ""
            ctk.CTkEntry(
                line, textvariable=var, placeholder_text=placeholder,
            ).pack(side="left", fill="x", expand=True)
            self._widgets[field.column] = var

    def _wire_inspections_autocalc(self) -> None:
        """Branche les auto-calculs sur le formulaire d'inspection.

        * ``ML Inspectés`` = |PK Arrivée − PK Départ| (en mètres)
        * ``Heures Totales`` = Heure Fin − Heure Début (heures décimales)

        Les valeurs saisies manuellement dans les champs calculés sont écrasées
        dès qu'une entrée source est modifiée : la source fait autorité.
        """
        pk_debut = self._widgets.get("pk_depart")
        pk_fin = self._widgets.get("pk_arrivee")
        ml_var = self._widgets.get("ml_inspectes")
        h_debut = self._widgets.get("heure_debut")
        h_fin = self._widgets.get("heure_fin")
        h_totales = self._widgets.get("heures_totales")

        def refresh_ml(*_: object) -> None:
            if ml_var is None or pk_debut is None or pk_fin is None:
                return
            result = compute_ml_inspectes(str(pk_debut.get()), str(pk_fin.get()))
            if result:
                ml_var.set(result)

        def refresh_heures(*_: object) -> None:
            if h_totales is None or h_debut is None or h_fin is None:
                return
            result = compute_heures_totales(str(h_debut.get()), str(h_fin.get()))
            if result:
                h_totales.set(result)

        for var in (pk_debut, pk_fin):
            if isinstance(var, ctk.StringVar):
                var.trace_add("write", refresh_ml)
        for var in (h_debut, h_fin):
            if isinstance(var, ctk.StringVar):
                var.trace_add("write", refresh_heures)

    def _collect(self) -> dict[str, str]:
        """Récupère les valeurs saisies, normalisées pour le stockage."""
        data: dict[str, str] = {}
        for field in self._service.form_fields(self._sheet):
            widget = self._widgets[field.column]
            if isinstance(widget, ctk.CTkTextbox):
                raw = widget.get("1.0", "end").strip()
            else:
                raw = str(widget.get()).strip()
            if raw == "—":
                raw = ""
            if field.widget == "date" and raw:
                raw = self._normalize_date(raw)
            data[field.column] = raw
        return data

    @staticmethod
    def _normalize_date(value: str) -> str:
        """Convertit une date saisie (JJ/MM/AAAA ou ISO) en ISO ``AAAA-MM-JJ``."""
        value = value.strip()
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, fmt).date().isoformat()
            except ValueError:
                continue
        return value

    def _save(self) -> None:
        """Valide et enregistre la ligne, puis ferme le formulaire."""
        data = self._collect()
        try:
            self._service.save_row(self._sheet, data, self._row_id)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Enregistrement", f"Échec : {exc}")
            return
        self._on_saved()
        self.destroy()


class AttachDocumentDialog(ctk.CTkToplevel):
    """Formulaire d'attachement d'un document à une entité (intervention/rapport)."""

    def __init__(
        self,
        master: ctk.CTk,
        service: RemoteDocumentService,
        source: Path,
        uploaded_by: str,
        on_attached: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self._service = service
        self._source = source
        self._uploaded_by = uploaded_by
        self._on_attached = on_attached

        self.title("Attacher un document")
        self.geometry("480x420")
        self.resizable(False, False)
        self.configure(fg_color=SURFACE)
        self.grab_set()

        head = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0)
        head.pack(fill="x")
        ctk.CTkLabel(
            head, text=f"Attacher : {source.name}",
            font=ctk.CTkFont(size=15, weight="bold"), text_color="white",
        ).pack(padx=16, pady=14, anchor="w")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=14)

        ctk.CTkLabel(body, text="Type d'entité", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x")
        self._entity_var = ctk.StringVar(value="rapports")
        ctk.CTkOptionMenu(
            body, values=["rapports", "inspections", "intervention", "incidents", "materiel"],
            variable=self._entity_var, fg_color=ACCENT, button_color=ACCENT_HOVER,
        ).pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(body, text="Identifiant / N° de l'entité", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x")
        self._entity_id_var = ctk.StringVar()
        ctk.CTkEntry(
            body, textvariable=self._entity_id_var, height=36,
            placeholder_text="ex. 43854 ou 12",
        ).pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(body, text="Notes (optionnel)", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x")
        self._notes_box = ctk.CTkTextbox(body, height=90)
        self._notes_box.pack(fill="x", pady=(2, 12))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(
            actions, text="💾  Attacher", fg_color=ACCENT, height=40,
            hover_color=ACCENT_HOVER, command=self._save,
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            actions, text="Annuler", fg_color="transparent",
            border_width=1, text_color=("black", "white"),
            height=40, width=110, command=self.destroy,
        ).pack(side="left", padx=(10, 0))

    def _save(self) -> None:
        """Persiste l'attachement du document."""
        entity_id = self._entity_id_var.get().strip()
        if not entity_id:
            messagebox.showwarning("Attacher", "L'identifiant est requis.")
            return
        try:
            self._service.attach(
                entity=self._entity_var.get(),
                entity_id=entity_id,
                source=self._source,
                uploaded_by=self._uploaded_by,
                notes=self._notes_box.get("1.0", "end").strip(),
            )
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Attachement", f"Échec : {exc}")
            return
        self._on_attached()
        self.destroy()


class UserFormDialog(ctk.CTkToplevel):
    """Formulaire de création d'un utilisateur (Admin uniquement)."""

    def __init__(
        self, master: ctk.CTk, auth: AuthService, on_saved: Callable[[], None]
    ) -> None:
        super().__init__(master)
        self._auth = auth
        self._on_saved = on_saved

        self.title("Nouvel utilisateur")
        self.geometry("460x460")
        self.resizable(False, False)
        self.configure(fg_color=SURFACE)
        self.grab_set()

        head = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0)
        head.pack(fill="x")
        ctk.CTkLabel(
            head, text="Créer un utilisateur",
            font=ctk.CTkFont(size=15, weight="bold"), text_color="white",
        ).pack(padx=16, pady=14, anchor="w")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=14)

        self._username = ctk.StringVar()
        self._full_name = ctk.StringVar()
        self._password = ctk.StringVar()
        self._role = ctk.StringVar(value=Role.CONSULTANT.value)

        for label, var, secret in [
            ("Nom d'utilisateur", self._username, False),
            ("Nom complet", self._full_name, False),
            ("Mot de passe", self._password, True),
        ]:
            ctk.CTkLabel(body, text=label, anchor="w",
                         font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x")
            ctk.CTkEntry(
                body, textvariable=var, height=36,
                show="•" if secret else "",
            ).pack(fill="x", pady=(2, 12))

        ctk.CTkLabel(body, text="Rôle", anchor="w",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(fill="x")
        ctk.CTkOptionMenu(
            body, values=[r.value for r in Role], variable=self._role,
            fg_color=ACCENT, button_color=ACCENT_HOVER,
        ).pack(fill="x", pady=(2, 12))

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkButton(
            actions, text="💾  Créer", fg_color=ACCENT, height=40,
            hover_color=ACCENT_HOVER, command=self._save,
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            actions, text="Annuler", fg_color="transparent",
            border_width=1, text_color=("black", "white"),
            height=40, width=110, command=self.destroy,
        ).pack(side="left", padx=(10, 0))

    def _save(self) -> None:
        """Persiste la création de l'utilisateur."""
        try:
            self._auth.create_user(
                username=self._username.get(),
                password=self._password.get(),
                role=Role.from_value(self._role.get()),
                full_name=self._full_name.get(),
            )
        except ValueError as exc:
            messagebox.showerror("Création", str(exc))
            return
        self._on_saved()
        self.destroy()


class PasswordChangeDialog(ctk.CTkToplevel):
    """Dialog de changement de mot de passe (Admin uniquement)."""

    def __init__(
        self, master: ctk.CTk, auth: AuthService, user: User,
        on_changed: Callable[[], None],
    ) -> None:
        super().__init__(master)
        self._auth = auth
        self._user = user
        self._on_changed = on_changed

        self.title("Modifier le mot de passe")
        self.geometry("420x260")
        self.resizable(False, False)
        self.configure(fg_color=SURFACE)
        self.grab_set()

        head = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0)
        head.pack(fill="x")
        ctk.CTkLabel(
            head, text=f"Nouveau mot de passe : {user.username}",
            font=ctk.CTkFont(size=14, weight="bold"), text_color="white",
        ).pack(padx=16, pady=14, anchor="w")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=14)

        self._password = ctk.StringVar()
        ctk.CTkEntry(
            body, textvariable=self._password, height=36,
            show="•", placeholder_text="Nouveau mot de passe",
        ).pack(fill="x", pady=(6, 14))

        ctk.CTkButton(
            body, text="💾  Enregistrer", fg_color=ACCENT, height=40,
            hover_color=ACCENT_HOVER, command=self._save,
        ).pack(fill="x")

    def _save(self) -> None:
        """Persiste le changement de mot de passe."""
        try:
            self._auth.change_password(int(self._user.id or 0), self._password.get())
        except ValueError as exc:
            messagebox.showerror("Modification", str(exc))
            return
        self._on_changed()
        self.destroy()


class BovoApp(ctk.CTk):
    """Fenêtre principale du logiciel."""

    def __init__(
        self,
        database: Database,
        settings: Settings,
        auth: AuthService | None = None,
        audit: AuditService | None = None,
        client: Any | None = None,
    ) -> None:
        super().__init__()
        self._db = database
        self._settings = settings
        self._auth = auth
        self._audit = audit
        # --- Mode REST (client injecté) ------------------------------- #
        # Depuis la migration REST du GUI, TOUTES les données métier
        # (interventions, modules ASF, documents) transitent par le
        # backend FastAPI. La DB SQLite locale ne sert plus qu'à trois
        # choses : paramètres, journal local, cache offline temporaire.
        if client is None and auth is not None:
            client = getattr(auth, "_client", None)
        if client is None:
            raise RuntimeError(
                "BovoApp requiert un ApiClient (mode REST). "
                "Passe `client=` explicitement ou via un RemoteAuthService.",
            )
        self._client = client
        self._planner = RemotePlanner(client)
        self._exporter = Exporter(database=None)  # export local à partir des interventions fournies
        self._inspections = RemoteInspectionService(client)
        self._documents = RemoteDocumentService(client)
        self._calendar_model = CalendarModel()
        self._progress_queue: queue.Queue[tuple] = queue.Queue()

        today = date.today()
        self._cal_year = today.year
        self._cal_month = today.month

        self.title("Bovo ASF Manager")
        width, height = settings.window_size
        self.geometry(f"{width}x{height}")
        self.minsize(1100, 720)
        self._apply_window_icon()
        self.withdraw()  # masquée tant que le splash + login ne sont pas terminés.

    # ------------------------------------------------------------------ #
    # Authentification & droits
    # ------------------------------------------------------------------ #
    def on_authenticated(self) -> None:
        """Appelé après une connexion réussie : construit l'UI puis l'affiche."""
        self._build_layout()
        default_view = "accueil"
        if not self._can("view_planning") and default_view == "accueil":
            default_view = "accueil"  # l'accueil reste accessible
        self._show_view(default_view)
        self.reveal()

    def _can(self, action: str) -> bool:
        """Raccourci de vérification de droits sur la session courante."""
        if self._auth is None:
            return True  # mode test / sans auth
        session = self._auth.session
        return {
            "edit": session.can_edit(),
            "view_planning": session.can_view_planning(),
            "manage_users": session.can_manage_users(),
            "view_audit": session.can_view_audit(),
        }.get(action, False)

    def _current_username(self) -> str:
        """Retourne le nom d'utilisateur courant (ou nom système)."""
        if self._auth is not None and self._auth.current_user is not None:
            return self._auth.current_user.username
        return get_system_username()

    @staticmethod
    def _role_label(role: Any) -> str:
        """Retourne l'étiquette d'un rôle (compat enum ``Role`` ou chaîne)."""
        return getattr(role, "value", None) or str(role)

    def _on_remote_event(self, payload: dict[str, Any]) -> None:
        """Callback invoqué par le listener SSE (déjà marshalé vers Tk main).

        Rafraîchit la vue courante quand une entité de son domaine est
        modifiée par un autre poste. Best-effort — ne crashe jamais.
        """
        entity = str(payload.get("entity", ""))
        try:
            active_key = next(
                (k for k, btn in self._nav_buttons.items()
                 if btn.cget("fg_color") == ACCENT),
                None,
            )
        except Exception:  # noqa: BLE001 - GUI en cours de destruction
            return
        if not active_key:
            return
        # Table de correspondance entité → vue à recharger.
        mapping = {
            "intervention": {"calendrier", "interventions", "accueil"},
            "module.inspections": {"inspections", "accueil"},
            "module.rapports": {"inspections"},
            "module.incidents": {"inspections"},
            "module.materiel": {"inspections"},
            "document": {"documents"},
            "user": {"utilisateurs"},
        }
        if active_key in mapping.get(entity, set()):
            try:
                self._show_view(active_key)
            except Exception:  # noqa: BLE001
                pass

    def _apply_window_icon(self) -> None:
        """Applique le logo BOVO comme icône de fenêtre (barre de tâches).

        Utilise ``iconphoto`` (Tk) compatible Windows/Linux/macOS via PIL.
        La référence à ``PhotoImage`` est conservée pour éviter la libération
        par le ramasse-miettes (l'icône disparaîtrait alors sur Windows).
        """
        logo_path = ASSETS_DIR / "logo.png"
        if not logo_path.exists():
            return
        try:
            from PIL import ImageTk  # import local pour ne pas alourdir le module
            image = Image.open(logo_path).convert("RGBA")
            image.thumbnail((256, 256), Image.LANCZOS)
            self._window_icon = ImageTk.PhotoImage(image)
            self.iconphoto(True, self._window_icon)
        except Exception as exc:  # noqa: BLE001 - icône best-effort.
            logger.warning("Impossible de définir l'icône : %s", exc)

    # ------------------------------------------------------------------ #
    # Construction de l'ossature
    # ------------------------------------------------------------------ #
    def _build_layout(self) -> None:
        """Construit la barre latérale et le conteneur de contenu."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, width=230, corner_radius=0, fg_color=CARD_BG)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        logo_path = ASSETS_DIR / "logo.png"
        if logo_path.exists():
            image = ctk.CTkImage(Image.open(logo_path), size=(96, 96))
            ctk.CTkLabel(sidebar, image=image, text="").pack(pady=(20, 4))
        ctk.CTkLabel(
            sidebar, text="Bovo ASF Manager",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=(0, 12))

        # ------------------------------------------------------------------ #
        # Pied fixe : version + utilisateur + déconnexion (packés d'abord
        # pour être TOUJOURS visibles, même avec beaucoup d'onglets).
        # ------------------------------------------------------------------ #
        ctk.CTkLabel(
            sidebar, text=f"v{__version__} · {__author__}",
            font=ctk.CTkFont(size=10), text_color="#7A7A80",
        ).pack(side="bottom", pady=(4, 10))

        if self._auth is not None and self._auth.current_user is not None:
            user = self._auth.current_user
            user_box = ctk.CTkFrame(sidebar, fg_color=SURFACE, corner_radius=10)
            user_box.pack(side="bottom", fill="x", padx=10, pady=(6, 6))
            ctk.CTkLabel(
                user_box, text=f"👤  {user.username}",
                font=ctk.CTkFont(size=12, weight="bold"), anchor="w",
                wraplength=200, justify="left",
            ).pack(fill="x", padx=10, pady=(8, 0))
            ctk.CTkLabel(
                user_box, text=self._role_label(user.role), text_color="#9A9AA0",
                font=ctk.CTkFont(size=10), anchor="w",
            ).pack(fill="x", padx=10, pady=(0, 4))
            ctk.CTkButton(
                user_box, text="⎋  Se déconnecter", height=34,
                fg_color=ACCENT, text_color="white",
                hover_color=ACCENT_HOVER,
                font=ctk.CTkFont(size=11, weight="bold"),
                command=self._logout,
            ).pack(fill="x", padx=10, pady=(2, 10))

        # ------------------------------------------------------------------ #
        # Nav scrollable au centre (accepte n'importe quel nombre d'onglets)
        # ------------------------------------------------------------------ #
        nav_container = ctk.CTkScrollableFrame(
            sidebar, fg_color="transparent",
            scrollbar_button_color=CARD_BG,
            scrollbar_button_hover_color=ACCENT,
        )
        nav_container.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 4))

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        self._nav_icons: dict[str, tuple[ctk.CTkImage, ctk.CTkImage]] = {}
        nav_items = self._nav_items_for_role()
        icons_dir = ASSETS_DIR / "icons"
        for key, label, icon_name in nav_items:
            # Charge les deux variantes (rouge = inactif, blanc = actif).
            red_path = icons_dir / f"{icon_name}.png"
            white_path = icons_dir / f"{icon_name}@white.png"
            icon_red = ctk.CTkImage(Image.open(red_path), size=(20, 20)) \
                if red_path.exists() else None
            icon_white = ctk.CTkImage(Image.open(white_path), size=(20, 20)) \
                if white_path.exists() else None
            if icon_red and icon_white:
                self._nav_icons[key] = (icon_red, icon_white)
            btn = ctk.CTkButton(
                nav_container, text=f"  {label}", anchor="w", height=42,
                fg_color="transparent", text_color=("black", "white"),
                hover_color=ACCENT, corner_radius=8,
                font=ctk.CTkFont(size=13, weight="bold"),
                image=icon_red, compound="left",
                command=lambda k=key: self._show_view(k),
            )
            btn.pack(fill="x", padx=6, pady=3)
            self._nav_buttons[key] = btn

        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=0, column=1, sticky="nsew", padx=24, pady=24)
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

    def _nav_items_for_role(self) -> list[tuple[str, str, str]]:
        """Retourne la liste des items de navigation autorisés au rôle courant.

        Chaque item est un tuple ``(key, label, icon)`` où ``icon`` est le
        nom d'un fichier PNG dans ``assets/icons/`` (sans extension). Les
        icônes sont chargées en deux variantes (rouge + blanche) et
        échangées selon l'état actif du bouton.

        Le Consultant n'accède pas au planning (Calendrier, Interventions,
        Importer PDF). Seul l'Admin voit « Utilisateurs ».
        """
        items: list[tuple[str, str, str]] = [("accueil", "Accueil", "home")]
        if self._can("view_planning"):
            items += [
                ("calendrier", "Calendrier", "calendar"),
                ("interventions", "Interventions", "search"),
            ]
        items += [
            ("inspections", "Inspections ASF", "tools"),
            ("documents", "Documents", "document"),
        ]
        if self._can("view_planning"):
            items += [("import", "Importer PDF", "upload")]
        if self._can("view_audit"):
            items += [("historique", "Historique", "clock")]
        if self._can("manage_users"):
            items += [("utilisateurs", "Utilisateurs", "users")]
        items += [
            ("journal", "Journal", "journal"),
            ("parametres", "Paramètres", "settings"),
        ]
        return items

    def _logout(self) -> None:
        """Déconnecte l'utilisateur et revient à l'écran de connexion."""
        if self._auth is None:
            return
        # On efface aussi la session mémorisée (le user demande à repartir de zéro).
        self._settings.forget()
        self._auth.logout()
        self.withdraw()
        for child in self.winfo_children():
            if not isinstance(child, ctk.CTkToplevel):
                child.destroy()
        LoginDialog(
            self, self._auth,
            on_success=self._relogin, on_cancel=self.on_close,
            settings=self._settings,
        )

    def _relogin(self) -> None:
        """Callback après relogin : rebuild UI selon nouveau rôle."""
        current = self._auth.current_user if self._auth else None
        if self._audit is not None and current is not None:
            self._audit.bind_session(current.username, self._role_label(current.role))
        self.on_authenticated()

    def _clear_content(self) -> None:
        """Vide la zone de contenu avant d'afficher une nouvelle vue."""
        for widget in self._content.winfo_children():
            widget.destroy()

    def _show_view(self, key: str) -> None:
        """Affiche la vue demandée et met en surbrillance l'onglet actif."""
        # Filtrage sécurité : si l'utilisateur n'a plus le droit d'accès, on
        # bascule sur « accueil ».
        allowed = {k for k, _, _ in self._nav_items_for_role()}
        if key not in allowed:
            key = "accueil"
        for nav_key, btn in self._nav_buttons.items():
            is_active = nav_key == key
            btn.configure(fg_color=ACCENT if is_active else "transparent")
            # Change l'icône selon l'état (blanche sur fond rouge, rouge sinon).
            icons = self._nav_icons.get(nav_key)
            if icons is not None:
                red_icon, white_icon = icons
                btn.configure(image=white_icon if is_active else red_icon)
        self._clear_content()
        builder = {
            "accueil": self._view_accueil,
            "calendrier": self._view_calendrier,
            "interventions": self._view_interventions,
            "inspections": self._view_inspections,
            "documents": self._view_documents,
            "import": self._view_import,
            "historique": self._view_historique,
            "utilisateurs": self._view_utilisateurs,
            "journal": self._view_journal,
            "parametres": self._view_parametres,
        }[key]
        builder()

    # ------------------------------------------------------------------ #
    # Vue : Accueil / Dashboard
    # ------------------------------------------------------------------ #
    def _view_accueil(self) -> None:
        """Affiche l'accueil avec salutation et tableau de bord."""
        frame = ctk.CTkScrollableFrame(self._content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        ctk.CTkLabel(
            frame, text=f"Bonjour {self._current_username()} 👋",
            font=ctk.CTkFont(size=28, weight="bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))
        ctk.CTkLabel(
            frame, text="Tableau de bord des interventions ASF",
            font=ctk.CTkFont(size=14), text_color="#9A9AA0",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 20))

        stats = self._planner.get_statistics()
        cards = [
            ("Interventions", stats["total"], ACCENT),
            ("PDF importés", stats["pdfs"], "#457B9D"),
            ("Terminées", stats["terminees"], "#43AA8B"),
            ("À faire", stats["a_faire"], "#F4A261"),
            ("Autoroutes", stats["autoroutes"], "#2A9D8F"),
            ("Secteurs", stats["secteurs"], "#9D4EDD"),
        ]
        for idx, (label, value, color) in enumerate(cards):
            self._stat_card(frame, label, str(value), color).grid(
                row=2 + idx // 4, column=idx % 4, padx=8, pady=8, sticky="nsew"
            )

        info = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=14)
        info.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(16, 0))
        ctk.CTkLabel(
            info, text=f"🗄️  Base de données : opérationnelle "
            f"·  Dernière mise à jour : {stats['derniere_maj']}",
            font=ctk.CTkFont(size=13),
        ).pack(anchor="w", padx=18, pady=14)

        kpis = self._inspections.kpis()
        ctk.CTkLabel(
            frame, text="Indicateurs ASF — Inspections ITV",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=5, column=0, columnspan=4, sticky="w", pady=(22, 8))
        kpi_cards = [
            ("ML inspectés", kpis["ml_inspectes"], "#457B9D"),
            ("Inspections", kpis["nb_inspections"], ACCENT),
            ("Regards", kpis["regards"], "#2A9D8F"),
            ("Heures totales", kpis["heures"], "#F4A261"),
            ("ML / heure", kpis["ml_h"], "#9D4EDD"),
        ]
        for idx, (label, value, color) in enumerate(kpi_cards):
            self._stat_card(frame, label, value, color).grid(
                row=6 + idx // 4, column=idx % 4, padx=8, pady=8, sticky="nsew"
            )

    def _stat_card(
        self, master: ctk.CTkBaseClass, label: str, value: str, color: str
    ) -> ctk.CTkFrame:
        """Construit une carte statistique colorée."""
        card = ctk.CTkFrame(master, fg_color=CARD_BG, corner_radius=14, height=110)
        card.grid_propagate(False)
        bar = ctk.CTkFrame(card, fg_color=color, width=6, corner_radius=3)
        bar.place(relx=0, rely=0.15, relheight=0.7)
        ctk.CTkLabel(
            card, text=value, font=ctk.CTkFont(size=30, weight="bold"),
        ).pack(anchor="w", padx=22, pady=(18, 0))
        ctk.CTkLabel(
            card, text=label, font=ctk.CTkFont(size=13), text_color="#9A9AA0",
        ).pack(anchor="w", padx=22)
        return card

    # ------------------------------------------------------------------ #
    # Vue : Calendrier
    # ------------------------------------------------------------------ #
    def _view_calendrier(self) -> None:
        """Affiche le calendrier mensuel interactif."""
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkButton(
            header, text="◀", width=44, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=lambda: self._change_month(-1),
        ).pack(side="left")
        self._month_label = ctk.CTkLabel(
            header, text=CalendarModel.month_label(self._cal_year, self._cal_month),
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        self._month_label.pack(side="left", padx=20)
        ctk.CTkButton(
            header, text="▶", width=44, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=lambda: self._change_month(1),
        ).pack(side="left")
        ctk.CTkButton(
            header, text="Aujourd'hui", fg_color="transparent",
            border_width=1, text_color=("black", "white"),
            command=self._goto_today,
        ).pack(side="left", padx=10)
        self._legend(header)

        grid_head = ctk.CTkFrame(frame, fg_color="transparent")
        grid_head.grid(row=1, column=0, sticky="ew")
        for col, name in enumerate(WEEKDAY_NAMES_FR):
            grid_head.grid_columnconfigure(col, weight=1)
            ctk.CTkLabel(
                grid_head, text=name, font=ctk.CTkFont(size=13, weight="bold"),
            ).grid(row=0, column=col, sticky="ew", pady=4)

        self._cal_grid = ctk.CTkFrame(frame, fg_color="transparent")
        self._cal_grid.grid(row=2, column=0, sticky="nsew")
        self._render_calendar_grid()

    def _legend(self, master: ctk.CTkBaseClass) -> None:
        """Affiche la légende des couleurs de statut."""
        box = ctk.CTkFrame(master, fg_color="transparent")
        box.pack(side="right")
        for statut, color in STATUT_COLORS.items():
            item = ctk.CTkFrame(box, fg_color="transparent")
            item.pack(side="left", padx=6)
            ctk.CTkFrame(item, fg_color=color, width=14, height=14, corner_radius=4).pack(
                side="left", padx=(0, 4)
            )
            ctk.CTkLabel(item, text=statut.value, font=ctk.CTkFont(size=11)).pack(
                side="left"
            )

    def _render_calendar_grid(self) -> None:
        """(Re)dessine la grille du mois courant."""
        for widget in self._cal_grid.winfo_children():
            widget.destroy()
        weeks = self._planner.build_calendar(self._cal_year, self._cal_month)
        for col in range(7):
            self._cal_grid.grid_columnconfigure(col, weight=1, uniform="day")
        for r in range(len(weeks)):
            self._cal_grid.grid_rowconfigure(r, weight=1, uniform="week")
        today = date.today()
        for r, week in enumerate(weeks):
            for c, cell in enumerate(week):
                self._build_day_cell(cell, r, c, today)

    def _build_day_cell(self, cell: DayCell, row: int, col: int, today: date) -> None:
        """Construit une case-jour cliquable du calendrier."""
        is_today = cell.day_date == today
        fg = SURFACE if cell.in_month else CARD_BG
        day_box = ctk.CTkFrame(
            self._cal_grid, fg_color=fg, corner_radius=10,
            border_width=2 if is_today else 0, border_color=ACCENT,
        )
        day_box.grid(row=row, column=col, sticky="nsew", padx=3, pady=3)
        text_color = ("black", "white") if cell.in_month else "#6C6C72"
        ctk.CTkLabel(
            day_box, text=str(cell.day_date.day),
            font=ctk.CTkFont(size=13, weight="bold"), text_color=text_color,
        ).pack(anchor="nw", padx=8, pady=(6, 0))

        if cell.count:
            badge = ctk.CTkButton(
                day_box, text=f"{cell.count} interv.",
                fg_color=cell.dominant_color, hover_color=ACCENT_HOVER,
                height=26, font=ctk.CTkFont(size=11, weight="bold"),
                command=lambda d=cell.day_date: self._open_day(d),
            )
            badge.pack(fill="x", padx=6, pady=6, side="bottom")

    def _open_day(self, day: date) -> None:
        """Ouvre la liste des interventions d'une journée."""
        iso = day.isoformat()
        interventions = self._planner.list_between(iso, iso)
        if len(interventions) == 1:
            self._open_detail(interventions[0])
            return
        win = ctk.CTkToplevel(self)
        win.title(f"Interventions du {format_date_fr(day)}")
        win.geometry("460x520")
        win.grab_set()
        scroll = ctk.CTkScrollableFrame(win, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=12)
        for iv in interventions:
            ctk.CTkButton(
                scroll, text=f"{iv.ouvrage} · {iv.objet} ({iv.statut.value})",
                anchor="w", fg_color=CARD_BG, text_color=("black", "white"),
                hover_color=ACCENT, height=40,
                command=lambda i=iv: self._open_detail(i),
            ).pack(fill="x", pady=4)

    def _change_month(self, delta: int) -> None:
        """Décale le mois affiché de ``delta`` (±1)."""
        month = self._cal_month + delta
        year = self._cal_year
        if month < 1:
            month, year = 12, year - 1
        elif month > 12:
            month, year = 1, year + 1
        self._cal_month, self._cal_year = month, year
        self._month_label.configure(
            text=CalendarModel.month_label(self._cal_year, self._cal_month)
        )
        self._render_calendar_grid()

    def _goto_today(self) -> None:
        """Revient au mois courant."""
        today = date.today()
        self._cal_year, self._cal_month = today.year, today.month
        self._month_label.configure(
            text=CalendarModel.month_label(self._cal_year, self._cal_month)
        )
        self._render_calendar_grid()

    # ------------------------------------------------------------------ #
    # Vue : Interventions / recherche
    # ------------------------------------------------------------------ #
    def _view_interventions(self) -> None:
        """Affiche la recherche instantanée et la liste des interventions."""
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew")
        self._search_var = ctk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._refresh_table())
        ctk.CTkEntry(
            toolbar, textvariable=self._search_var,
            placeholder_text="Rechercher (ouvrage, autoroute, secteur, type…)",
            height=40,
        ).pack(side="left", fill="x", expand=True)

        options = self._planner.filter_options()
        self._statut_var = ctk.StringVar(value="Tous statuts")
        ctk.CTkOptionMenu(
            toolbar, values=["Tous statuts", *options["statuts"]],
            variable=self._statut_var, command=lambda _: self._refresh_table(),
            fg_color=ACCENT, button_color=ACCENT_HOVER, width=150,
        ).pack(side="left", padx=8)
        self._auto_var = ctk.StringVar(value="Toutes autoroutes")
        ctk.CTkOptionMenu(
            toolbar, values=["Toutes autoroutes", *options["autoroutes"]],
            variable=self._auto_var, command=lambda _: self._refresh_table(),
            fg_color=ACCENT, button_color=ACCENT_HOVER, width=160,
        ).pack(side="left", padx=4)

        exports = ctk.CTkFrame(frame, fg_color="transparent")
        exports.grid(row=1, column=0, sticky="ew", pady=10)
        ctk.CTkLabel(exports, text="Exporter :").pack(side="left")
        for label, fmt in [("Excel", "xlsx"), ("CSV", "csv"), ("JSON", "json"), ("PDF", "pdf")]:
            ctk.CTkButton(
                exports, text=label, width=80, fg_color=CARD_BG,
                text_color=("black", "white"), hover_color=ACCENT,
                command=lambda f=fmt: self._export(f),
            ).pack(side="left", padx=4)
        self._count_label = ctk.CTkLabel(exports, text="", text_color="#9A9AA0")
        self._count_label.pack(side="right")

        self._table = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self._table.grid(row=2, column=0, sticky="nsew")
        self._refresh_table()

    def _current_filters(self) -> dict[str, str]:
        """Lit les filtres actifs de la vue interventions."""
        statut = self._statut_var.get()
        auto = self._auto_var.get()
        return {
            "search": self._search_var.get().strip(),
            "statut": "" if statut == "Tous statuts" else statut,
            "autoroute": "" if auto == "Toutes autoroutes" else auto,
        }

    def _refresh_table(self) -> None:
        """Recharge la liste des interventions selon les filtres."""
        for widget in self._table.winfo_children():
            widget.destroy()
        interventions = self._planner.search(**self._current_filters())
        self._count_label.configure(text=f"{len(interventions)} résultat(s)")

        head = ctk.CTkFrame(self._table, fg_color=CARD_BG, corner_radius=8)
        head.pack(fill="x", pady=(0, 4))
        headers = ["Ouvrage", "Objet", "Autoroute", "Dates", "Type", "Statut"]
        widths = [110, 150, 90, 180, 130, 110]
        for text, w in zip(headers, widths, strict=False):
            ctk.CTkLabel(
                head, text=text, width=w, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", padx=6, pady=8)

        for iv in interventions:
            self._table_row(iv, widths)

    def _table_row(self, iv: Intervention, widths: list[int]) -> None:
        """Construit une ligne cliquable de la table des interventions."""
        row = ctk.CTkFrame(self._table, fg_color=SURFACE, height=40, corner_radius=8)
        row.pack(fill="x", pady=2)
        dates = (
            f"{format_date_fr(iv.date_debut)} → {format_date_fr(iv.date_fin)}"
            if iv.date_debut else "—"
        )
        cells = [
            iv.ouvrage, iv.objet, iv.autoroute, dates,
            iv.type_ouvrage or "—", iv.statut.value,
        ]
        handler = lambda _event=None, i=iv: self._open_detail(i)  # noqa: E731
        row.bind("<Button-1>", handler)
        for col, (value, width) in enumerate(zip(cells, widths, strict=False)):
            is_statut = col == len(cells) - 1
            label = ctk.CTkLabel(
                row, text=value, width=width, anchor="w",
                text_color=STATUT_COLORS.get(iv.statut) if is_statut else ("black", "white"),
                font=ctk.CTkFont(size=12),
            )
            label.pack(side="left", padx=6, pady=8)
            label.bind("<Button-1>", handler)

    def _open_detail(self, iv: Intervention) -> None:
        """Ouvre la fiche détaillée d'une intervention."""
        InterventionDialog(self, iv, self._on_status_change)

    def _on_status_change(
        self, iv: Intervention, statut: StatutIntervention
    ) -> None:
        """Persiste un changement de statut depuis la fiche détaillée."""
        if iv.id is not None:
            self._planner.set_statut(iv.id, statut)
            iv.statut = statut

    def _export(self, fmt: str) -> None:
        """Exporte les interventions filtrées dans le format choisi."""
        interventions = self._planner.search(**self._current_filters())
        if not interventions:
            messagebox.showinfo("Export", "Aucune intervention à exporter.")
            return
        extension = {"xlsx": ".xlsx", "csv": ".csv", "json": ".json", "pdf": ".pdf"}[fmt]
        path = filedialog.asksaveasfilename(
            title="Enregistrer l'export",
            initialdir=str(self._settings.export_folder),
            defaultextension=extension,
            initialfile=f"interventions_bovo{extension}",
        )
        if not path:
            return
        dispatch = {
            "xlsx": self._exporter.to_excel,
            "csv": self._exporter.to_csv,
            "json": self._exporter.to_json,
            "pdf": self._exporter.to_pdf,
        }[fmt]
        try:
            dispatch(interventions, Path(path))
            messagebox.showinfo("Export", f"Export réussi :\n{path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Export", f"Échec de l'export : {exc}")

    # ------------------------------------------------------------------ #
    # Vue : Import
    # ------------------------------------------------------------------ #
    def _view_import(self) -> None:
        """Affiche la vue d'import de PDF avec barre de progression."""
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame, text="Importer des interventions",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 4))
        ctk.CTkLabel(
            frame, text="Sélectionnez un ou plusieurs PDF, ou un dossier complet. "
            "Le logiciel fait automatiquement le reste.",
            text_color="#9A9AA0", wraplength=700, justify="left",
        ).grid(row=1, column=0, sticky="w", pady=(0, 20))

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="w")
        ctk.CTkButton(
            buttons, text="📄  Choisir des PDF", height=50, fg_color=ACCENT,
            hover_color=ACCENT_HOVER, command=self._pick_pdfs,
        ).pack(side="left", padx=(0, 10))
        ctk.CTkButton(
            buttons, text="📁  Choisir un dossier", height=50, fg_color="#457B9D",
            hover_color="#35617D", command=self._pick_folder,
        ).pack(side="left")

        self._progress = ctk.CTkProgressBar(frame, height=16)
        self._progress.grid(row=3, column=0, sticky="ew", pady=(28, 6))
        self._progress.set(0)
        self._progress_label = ctk.CTkLabel(frame, text="En attente d'import…")
        self._progress_label.grid(row=4, column=0, sticky="w")

        self._import_log = ctk.CTkTextbox(frame, height=220)
        self._import_log.grid(row=5, column=0, sticky="nsew", pady=16)
        frame.grid_rowconfigure(5, weight=1)
        self._import_log.insert("end", "Journal d'import prêt.\n")
        self._import_log.configure(state="disabled")

    def _pick_pdfs(self) -> None:
        """Ouvre un sélecteur de fichiers PDF."""
        paths = filedialog.askopenfilenames(
            title="Sélectionner des PDF",
            initialdir=str(self._settings.pdf_folder),
            filetypes=[("Fichiers PDF", "*.pdf")],
        )
        if paths:
            self._start_import([Path(p) for p in paths])

    def _pick_folder(self) -> None:
        """Ouvre un sélecteur de dossier de PDF."""
        folder = filedialog.askdirectory(
            title="Sélectionner un dossier",
            initialdir=str(self._settings.pdf_folder),
        )
        if folder:
            self._settings.set("pdf_folder", folder)
            self._start_import(sorted(Path(folder).rglob("*.pdf")))

    def _start_import(self, pdf_paths: list[Path]) -> None:
        """Lance l'import dans un thread et active le suivi de progression."""
        if not pdf_paths:
            messagebox.showinfo("Import", "Aucun PDF sélectionné.")
            return
        self._progress.set(0)
        self._append_import_log(f"Démarrage : {len(pdf_paths)} fichier(s).")

        def worker() -> None:
            def progress(current: int, total: int, message: str) -> None:
                self._progress_queue.put(("progress", current, total, message))

            result = self._planner.import_pdfs(pdf_paths, progress)
            self._progress_queue.put(("done", result))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_progress()

    def _poll_progress(self) -> None:
        """Consomme la file de progression et met à jour l'UI (thread principal)."""
        try:
            while True:
                event = self._progress_queue.get_nowait()
                if event[0] == "progress":
                    _, current, total, message = event
                    self._progress.set(current / total if total else 0)
                    self._progress_label.configure(text=f"{current}/{total} · {message}")
                    self._append_import_log(message)
                elif event[0] == "done":
                    self._finish_import(event[1])
                    return
        except queue.Empty:
            pass
        self.after(120, self._poll_progress)

    def _finish_import(self, result: ImportResult) -> None:
        """Finalise l'import : récapitulatif et notification."""
        self._progress.set(1)
        self._progress_label.configure(text="Import terminé.")
        summary = (
            f"✅ {result.files_processed} fichier(s) · "
            f"{result.interventions_created} créées · "
            f"{result.interventions_updated} mises à jour."
        )
        self._append_import_log(summary)
        for err in result.errors:
            self._append_import_log(f"⚠️ {err}")
        messagebox.showinfo("Import terminé", summary)

    def _append_import_log(self, text: str) -> None:
        """Ajoute une ligne au journal d'import affiché."""
        self._import_log.configure(state="normal")
        self._import_log.insert("end", f"{text}\n")
        self._import_log.see("end")
        self._import_log.configure(state="disabled")

    # ------------------------------------------------------------------ #
    # Vue : Inspections ASF (modules éditables du classeur)
    # ------------------------------------------------------------------ #
    def _view_inspections(self) -> None:
        """Affiche les modules ASF éditables (onglets) + import du classeur."""
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        title_box = ctk.CTkFrame(header, fg_color="transparent")
        title_box.pack(side="left")
        ctk.CTkLabel(
            title_box, text="Inspections ASF (ITV)",
            font=ctk.CTkFont(size=26, weight="bold"),
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_box,
            text="Mise en page conforme au formulaire ASF « Visites assainissement V2026-06-01 »",
            text_color="#8A8A90", font=ctk.CTkFont(size=12),
        ).pack(anchor="w")
        if self._can("edit"):
            ctk.CTkButton(
                header, text="📊  Importer le classeur Excel", fg_color="#43AA8B",
                hover_color="#369072", height=40,
                command=self._import_workbook,
            ).pack(side="right")

        # Barre de KPIs ASF (compte par module) — grand bandeau lisible.
        stats_bar = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=12)
        stats_bar.grid(row=1, column=0, sticky="ew", pady=(6, 14))
        self._module_stat_labels: dict[str, ctk.CTkLabel] = {}
        colors = {"inspections": ACCENT, "rapports": "#457B9D",
                  "incidents": "#F4A261", "materiel": "#2A9D8F"}
        for i, sheet in enumerate(self._inspections.SHEETS):
            box = ctk.CTkFrame(stats_bar, fg_color="transparent")
            box.grid(row=0, column=i, padx=18, pady=14, sticky="w")
            stats_bar.grid_columnconfigure(i, weight=1)
            color = colors.get(sheet, ACCENT)
            ctk.CTkFrame(
                box, fg_color=color, width=6, height=42, corner_radius=3
            ).pack(side="left", padx=(0, 12))
            info = ctk.CTkFrame(box, fg_color="transparent")
            info.pack(side="left")
            count_lbl = ctk.CTkLabel(
                info, text="0", anchor="w",
                font=ctk.CTkFont(size=22, weight="bold"),
            )
            count_lbl.pack(anchor="w")
            ctk.CTkLabel(
                info, text=self._inspections.sheet_label(sheet),
                text_color="#8A8A90", font=ctk.CTkFont(size=11), anchor="w",
            ).pack(anchor="w")
            self._module_stat_labels[sheet] = count_lbl

        tabview = ctk.CTkTabview(frame, fg_color=CARD_BG)
        tabview.grid(row=2, column=0, sticky="nsew")

        self._insp_search: dict[str, ctk.StringVar] = {}
        self._insp_tables: dict[str, ctk.CTkScrollableFrame] = {}
        for sheet in self._inspections.SHEETS:
            tab = tabview.add(self._inspections.sheet_label(sheet))
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(1, weight=1)
            self._build_module_tab(tab, sheet)
            self._refresh_module(sheet)

    def _build_module_tab(self, parent: ctk.CTkBaseClass, sheet: str) -> None:
        """Construit la barre d'outils et la table d'un module ASF."""
        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=8)
        search_var = ctk.StringVar()
        search_var.trace_add("write", lambda *_s, sh=sheet: self._refresh_module(sh))
        self._insp_search[sheet] = search_var
        ctk.CTkEntry(
            toolbar, textvariable=search_var, height=36,
            placeholder_text=f"Rechercher dans {self._inspections.sheet_label(sheet)}…",
        ).pack(side="left", fill="x", expand=True, padx=(4, 8))
        ctk.CTkButton(
            toolbar, text="📄  Export PDF", width=130, fg_color="#457B9D",
            hover_color="#35617D",
            command=lambda sh=sheet: self._export_module_pdf(sh),
        ).pack(side="right", padx=4)
        if self._can("edit"):
            ctk.CTkButton(
                toolbar, text="➕  Ajouter", width=120, fg_color=ACCENT,
                hover_color=ACCENT_HOVER,
                command=lambda sh=sheet: self._open_row_form(sh, None),
            ).pack(side="right", padx=4)

        table = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        table.grid(row=1, column=0, sticky="nsew")
        self._insp_tables[sheet] = table

    def _export_module_pdf(self, sheet: str) -> None:
        """Exporte un module ASF au format PDF tableur (paysage)."""
        rows = self._inspections.list_rows(sheet)
        if not rows:
            messagebox.showinfo("Export", "Aucune donnée à exporter.")
            return
        label = self._inspections.sheet_label(sheet).replace(" ", "_").replace("'", "")
        path = filedialog.asksaveasfilename(
            title="Exporter en PDF (tableur)",
            initialdir=str(self._settings.export_folder),
            defaultextension=".pdf",
            initialfile=f"bovo_{label.lower()}.pdf",
            filetypes=[("Fichier PDF", "*.pdf")],
        )
        if not path:
            return
        try:
            self._inspections.export_pdf(sheet, Path(path))
            messagebox.showinfo("Export", f"Export réussi :\n{path}")
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Export", f"Échec de l'export : {exc}")

    def _refresh_module(self, sheet: str) -> None:
        """Recharge la table d'un module ASF selon la recherche."""
        table = self._insp_tables[sheet]
        for widget in table.winfo_children():
            widget.destroy()
        columns = self._inspections.list_columns(sheet)
        rows = self._inspections.list_rows(sheet, self._insp_search[sheet].get().strip())

        # Met à jour le compteur affiché dans la barre de KPIs.
        stat_lbl = getattr(self, "_module_stat_labels", {}).get(sheet)
        if stat_lbl is not None:
            stat_lbl.configure(text=str(len(rows)))

        head = ctk.CTkFrame(table, fg_color=CARD_BG, corner_radius=8)
        head.pack(fill="x", pady=(0, 4))
        for _col, label in columns:
            ctk.CTkLabel(
                head, text=label, width=150, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", padx=6, pady=8)
        ctk.CTkLabel(head, text="", width=80).pack(side="left")

        if not rows:
            empty = ctk.CTkFrame(table, fg_color=SURFACE, corner_radius=10)
            empty.pack(fill="x", pady=20)
            ctk.CTkLabel(
                empty, text="🗂️", font=ctk.CTkFont(size=32),
            ).pack(pady=(16, 4))
            ctk.CTkLabel(
                empty,
                text="Aucune donnée dans ce module.",
                text_color="#9A9AA0", font=ctk.CTkFont(size=13, weight="bold"),
            ).pack()
            ctk.CTkLabel(
                empty,
                text="Cliquez sur « ➕ Ajouter » ou importez le classeur Excel ASF.",
                text_color="#7A7A80", font=ctk.CTkFont(size=11),
            ).pack(pady=(2, 16))
            return

        for row in rows:
            self._module_row(sheet, row, columns)

    def _module_row(
        self, sheet: str, row: dict[str, str], columns: list[tuple[str, str]]
    ) -> None:
        """Construit une ligne de table de module (éditable + suppression)."""
        container = ctk.CTkFrame(
            self._insp_tables[sheet], fg_color=SURFACE, height=44, corner_radius=8,
            border_width=0,
        )
        container.pack(fill="x", pady=3)
        row_id = int(row["id"])
        handler = lambda _e=None, sh=sheet, rid=row_id: self._open_row_form(sh, rid)  # noqa: E731
        if self._can("edit"):
            container.bind("<Button-1>", handler)
        # Couleurs par statut / urgence / etat_cunettes (badges lisibles).
        _STATUS_COLORS = {
            "Terminée": "#2A9D8F", "En cours": "#F4A261",
            "Planifiée": "#457B9D", "À faire": "#8A8A90", "Annulée": "#E63946",
            "Pas de défaut": "#2A9D8F", "Non évolutif": "#457B9D",
            "Evolution normale": "#F4A261", "Défauts majeurs": "#E63946",
            "Non visitable": "#8A8A90",
            "Aucune": "#2A9D8F", "Moindre": "#457B9D",
            "Moyenne": "#F4A261", "Elevée": "#E63946", "Très elevée": "#E63946",
        }
        for col, _label in columns:
            value = row.get(col, "") or "—"
            if col == "date":
                value = format_date_fr(parse_iso_date(row.get(col))) or value
            # Badges colorés pour les colonnes de statut/urgence/état.
            if col in ("statut", "urgence", "etat_cunettes") and value != "—":
                color = _STATUS_COLORS.get(value, ACCENT)
                badge = ctk.CTkLabel(
                    container, text=f"  {value}  ", width=150,
                    fg_color=color, text_color="white", corner_radius=6,
                    font=ctk.CTkFont(size=11, weight="bold"),
                )
                badge.pack(side="left", padx=6, pady=8)
                if self._can("edit"):
                    badge.bind("<Button-1>", handler)
                continue
            label = ctk.CTkLabel(
                container, text=str(value)[:28], width=150, anchor="w",
                font=ctk.CTkFont(size=12),
            )
            label.pack(side="left", padx=6, pady=8)
            if self._can("edit"):
                label.bind("<Button-1>", handler)
        if self._can("edit"):
            ctk.CTkButton(
                container, text="🗑", width=36, fg_color="transparent",
                text_color=ACCENT, hover_color=CARD_BG,
                command=lambda sh=sheet, rid=row_id: self._delete_module_row(sh, rid),
            ).pack(side="right", padx=6)

    def _delete_module_row(self, sheet: str, row_id: int) -> None:
        """Supprime une ligne de module après confirmation."""
        if messagebox.askyesno("Suppression", "Supprimer cette entrée ?"):
            self._inspections.delete_row(sheet, row_id)
            self._refresh_module(sheet)

    def _open_row_form(self, sheet: str, row_id: int | None) -> None:
        """Ouvre le formulaire d'ajout/édition d'une ligne de module."""
        RowFormDialog(
            self, self._inspections, sheet, row_id,
            on_saved=lambda: self._refresh_module(sheet),
        )

    def _import_workbook(self) -> None:
        """Importe le classeur Excel ASF et synchronise les interventions."""
        path = filedialog.askopenfilename(
            title="Sélectionner le classeur Excel ASF",
            initialdir=str(self._settings.pdf_folder),
            filetypes=[("Classeur Excel", "*.xlsx")],
        )
        if not path:
            return
        try:
            summary = self._inspections.import_workbook(Path(path))
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Import", f"Échec de l'import : {exc}")
            return
        for sheet in self._inspections.SHEETS:
            self._refresh_module(sheet)
        messagebox.showinfo(
            "Import réussi",
            "Classeur importé :\n"
            f"• Inspections : {summary.get('inspections', 0)}\n"
            f"• Rapports : {summary.get('rapports', 0)}\n"
            f"• Incidents : {summary.get('incidents', 0)}\n"
            f"• Matériel : {summary.get('materiel', 0)}\n"
            f"• Interventions marquées « Terminée » : "
            f"{summary.get('interventions_liees', 0)}",
        )

    # ------------------------------------------------------------------ #
    # Vue : Gestion documentaire
    # ------------------------------------------------------------------ #
    def _view_documents(self) -> None:
        """Affiche la liste des documents attachés, avec ajout/suppression."""
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(
            header, text="Documents attachés",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")
        if self._can("edit"):
            ctk.CTkButton(
                header, text="📎  Attacher un document", fg_color=ACCENT,
                hover_color=ACCENT_HOVER, command=self._attach_document,
            ).pack(side="right")

        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self._doc_search_var = ctk.StringVar()
        self._doc_search_var.trace_add("write", lambda *_: self._refresh_documents())
        ctk.CTkEntry(
            toolbar, textvariable=self._doc_search_var, height=36,
            placeholder_text="Rechercher (fichier, note)…",
        ).pack(side="left", fill="x", expand=True)

        self._doc_table = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self._doc_table.grid(row=2, column=0, sticky="nsew")
        self._refresh_documents()

    def _refresh_documents(self) -> None:
        """Recharge la liste des documents selon la recherche courante."""
        for widget in self._doc_table.winfo_children():
            widget.destroy()
        documents = self._documents.list_all(self._doc_search_var.get().strip())

        head = ctk.CTkFrame(self._doc_table, fg_color=CARD_BG, corner_radius=8)
        head.pack(fill="x", pady=(0, 4))
        for text, w in [
            ("Fichier", 260), ("Entité", 130), ("Taille", 90),
            ("Par", 140), ("Date", 170),
        ]:
            ctk.CTkLabel(
                head, text=text, width=w, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", padx=6, pady=8)

        if not documents:
            ctk.CTkLabel(
                self._doc_table,
                text="Aucun document. Cliquez « Attacher un document » pour commencer.",
                text_color="#9A9AA0",
            ).pack(anchor="w", pady=20)
            return

        for doc in documents:
            self._doc_row(doc)

    def _doc_row(self, doc: Document) -> None:
        """Construit une ligne de la table Documents."""
        row = ctk.CTkFrame(self._doc_table, fg_color=SURFACE, height=40, corner_radius=8)
        row.pack(fill="x", pady=2)
        date_str = doc.uploaded_at[:19].replace("T", " ")
        cells = [
            (doc.filename, 260),
            (f"{doc.entity} #{doc.entity_id}", 130),
            (doc.size_readable, 90),
            (doc.uploaded_by, 140),
            (date_str, 170),
        ]
        for value, w in cells:
            ctk.CTkLabel(
                row, text=str(value)[:60], width=w, anchor="w",
                font=ctk.CTkFont(size=12),
            ).pack(side="left", padx=6, pady=8)
        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.pack(side="right", padx=6)
        ctk.CTkButton(
            actions, text="Ouvrir", width=76, fg_color=CARD_BG,
            text_color=("black", "white"), hover_color=ACCENT,
            command=lambda d=doc: self._open_document(d),
        ).pack(side="left", padx=2)
        if self._can("edit"):
            ctk.CTkButton(
                actions, text="🗑", width=36, fg_color="transparent",
                text_color=ACCENT, hover_color=CARD_BG,
                command=lambda d=doc: self._delete_document(d),
            ).pack(side="left", padx=2)

    def _attach_document(self) -> None:
        """Ouvre un sélecteur de fichier et rattache le document choisi."""
        path = filedialog.askopenfilename(
            title="Sélectionner un document",
            initialdir=str(self._settings.pdf_folder),
            filetypes=[
                ("Documents", "*.pdf *.png *.jpg *.jpeg *.webp *.docx *.xlsx *.txt"),
                ("Tous les fichiers", "*.*"),
            ],
        )
        if not path:
            return
        dialog = AttachDocumentDialog(
            self, self._documents, Path(path), self._current_username(),
            on_attached=self._refresh_documents,
        )
        self.wait_window(dialog)

    def _open_document(self, doc: Document) -> None:
        """Télécharge le document du serveur puis l'ouvre en application native."""
        import tempfile
        # En mode REST, le fichier vit sur le serveur : on télécharge dans
        # un cache local temporaire avant l'ouverture native.
        cache_dir = Path(tempfile.gettempdir()) / "bovo-docs"
        cache_dir.mkdir(parents=True, exist_ok=True)
        target = cache_dir / f"{doc.id}_{doc.filename}"
        try:
            self._documents.download(doc, target)
        except Exception as exc:  # noqa: BLE001 — I/O ou API
            messagebox.showwarning("Document", f"Téléchargement échoué : {exc}")
            return
        if not open_file_native(target):
            messagebox.showwarning("Document", "Impossible d'ouvrir le fichier.")

    def _delete_document(self, doc: Document) -> None:
        """Supprime un document attaché (base + fichier)."""
        if not messagebox.askyesno("Suppression", f"Supprimer « {doc.filename} » ?"):
            return
        self._documents.delete(doc.id)
        if self._audit is not None:
            self._audit.record(
                action="delete", entity="document", entity_id=str(doc.id),
                before={"filename": doc.filename, "entity": doc.entity},
                after={},
            )
        self._refresh_documents()

    # ------------------------------------------------------------------ #
    # Vue : Historique (audit trail)
    # ------------------------------------------------------------------ #
    def _view_historique(self) -> None:
        """Affiche l'audit trail (qui a modifié quoi et quand)."""
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            frame, text="Historique des modifications",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        toolbar = ctk.CTkFrame(frame, fg_color="transparent")
        toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        self._audit_search_var = ctk.StringVar()
        self._audit_search_var.trace_add("write", lambda *_: self._refresh_audit())
        ctk.CTkEntry(
            toolbar, textvariable=self._audit_search_var, height=36,
            placeholder_text="Rechercher (utilisateur, entité, valeur…)",
        ).pack(side="left", fill="x", expand=True)
        self._audit_entity_var = ctk.StringVar(value="Toutes entités")
        ctk.CTkOptionMenu(
            toolbar, values=[
                "Toutes entités", "intervention", "inspections",
                "rapports", "incidents", "materiel", "document",
            ],
            variable=self._audit_entity_var,
            command=lambda _: self._refresh_audit(),
            fg_color=ACCENT, button_color=ACCENT_HOVER, width=170,
        ).pack(side="left", padx=8)

        self._audit_table = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self._audit_table.grid(row=2, column=0, sticky="nsew")
        self._refresh_audit()

    def _refresh_audit(self) -> None:
        """Recharge la liste des entrées d'audit selon les filtres."""
        for widget in self._audit_table.winfo_children():
            widget.destroy()
        if self._audit is None:
            ctk.CTkLabel(
                self._audit_table, text="Historique non disponible.",
                text_color="#9A9AA0",
            ).pack(anchor="w", pady=20)
            return
        entity = self._audit_entity_var.get()
        entity = "" if entity == "Toutes entités" else entity
        entries = self._audit.list_entries(
            limit=300, entity=entity, search=self._audit_search_var.get().strip(),
        )
        if not entries:
            ctk.CTkLabel(
                self._audit_table, text="Aucune modification pour ces critères.",
                text_color="#9A9AA0",
            ).pack(anchor="w", pady=20)
            return
        for entry in entries:
            self._audit_row(entry)

    def _audit_row(self, entry: AuditEntry) -> None:
        """Construit une ligne de l'audit trail."""
        color_by_action = {
            "create": "#43AA8B", "update": "#457B9D", "delete": ACCENT,
        }
        card = ctk.CTkFrame(self._audit_table, fg_color=SURFACE, corner_radius=8)
        card.pack(fill="x", pady=2)
        head = ctk.CTkFrame(card, fg_color="transparent")
        head.pack(fill="x", padx=10, pady=(8, 2))
        ctk.CTkLabel(
            head, text=entry.action.upper(), width=70, anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"),
            text_color=color_by_action.get(entry.action, "#9A9AA0"),
        ).pack(side="left")
        ctk.CTkLabel(
            head, text=f"{entry.entity} #{entry.entity_id}", anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=(4, 12))
        ctk.CTkLabel(
            head, text=f"par {entry.username} ({entry.role})",
            font=ctk.CTkFont(size=11), text_color="#9A9AA0",
        ).pack(side="left")
        ctk.CTkLabel(
            head, text=entry.created_at[:19].replace("T", " "),
            font=ctk.CTkFont(size=11), text_color="#9A9AA0",
        ).pack(side="right")

        diff = entry.diff()
        if diff:
            body = ctk.CTkFrame(card, fg_color="transparent")
            body.pack(fill="x", padx=10, pady=(0, 8))
            for field_name, before, after in diff[:8]:
                line = ctk.CTkFrame(body, fg_color="transparent")
                line.pack(fill="x", pady=1)
                ctk.CTkLabel(
                    line, text=field_name, width=140, anchor="w",
                    font=ctk.CTkFont(size=11, weight="bold"),
                ).pack(side="left")
                ctk.CTkLabel(
                    line, text=f"{before or '∅'} → {after or '∅'}", anchor="w",
                    font=ctk.CTkFont(size=11), text_color="#9A9AA0",
                    wraplength=520, justify="left",
                ).pack(side="left", fill="x", expand=True)

    # ------------------------------------------------------------------ #
    # Vue : Utilisateurs (Admin uniquement)
    # ------------------------------------------------------------------ #
    def _view_utilisateurs(self) -> None:
        """Écran de gestion des utilisateurs, accessible uniquement à l'Admin."""
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(
            header, text="Utilisateurs & rôles",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            header, text="➕  Nouvel utilisateur", fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=lambda: self._open_user_form(None),
        ).pack(side="right")

        self._user_table = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        self._user_table.grid(row=2, column=0, sticky="nsew")
        self._refresh_users()

    def _refresh_users(self) -> None:
        """Recharge la liste des utilisateurs."""
        for widget in self._user_table.winfo_children():
            widget.destroy()
        if self._auth is None:
            return
        head = ctk.CTkFrame(self._user_table, fg_color=CARD_BG, corner_radius=8)
        head.pack(fill="x", pady=(0, 4))
        for text, w in [
            ("Utilisateur", 200), ("Nom complet", 220),
            ("Rôle", 160), ("Dernière connexion", 200),
        ]:
            ctk.CTkLabel(
                head, text=text, width=w, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", padx=6, pady=8)
        for user in self._auth.list_users():
            self._user_row(user)

    def _user_row(self, user: User) -> None:
        """Construit une ligne de la table utilisateurs."""
        row = ctk.CTkFrame(self._user_table, fg_color=SURFACE, height=40, corner_radius=8)
        row.pack(fill="x", pady=2)
        last = user.last_login[:19].replace("T", " ") if user.last_login else "—"
        for value, w in [
            (user.username, 200), (user.full_name or "—", 220),
            (self._role_label(user.role), 160), (last, 200),
        ]:
            ctk.CTkLabel(
                row, text=str(value)[:60], width=w, anchor="w",
                font=ctk.CTkFont(size=12),
            ).pack(side="left", padx=6, pady=8)
        actions = ctk.CTkFrame(row, fg_color="transparent")
        actions.pack(side="right", padx=6)
        ctk.CTkButton(
            actions, text="🔑  MdP", width=80, fg_color=CARD_BG,
            text_color=("black", "white"), hover_color=ACCENT,
            command=lambda u=user: self._change_user_password(u),
        ).pack(side="left", padx=2)
        current = self._auth.current_user if self._auth else None
        if current is None or current.id != user.id:
            ctk.CTkButton(
                actions, text="🗑", width=36, fg_color="transparent",
                text_color=ACCENT, hover_color=CARD_BG,
                command=lambda u=user: self._delete_user(u),
            ).pack(side="left", padx=2)

    def _open_user_form(self, user: User | None) -> None:
        """Ouvre le formulaire de création d'utilisateur."""
        if self._auth is None:
            return
        UserFormDialog(self, self._auth, on_saved=self._refresh_users)

    def _change_user_password(self, user: User) -> None:
        """Ouvre un dialog de changement de mot de passe."""
        if self._auth is None or user.id is None:
            return
        PasswordChangeDialog(
            self, self._auth, user, on_changed=self._refresh_users,
        )

    def _delete_user(self, user: User) -> None:
        """Supprime un utilisateur (Admin uniquement)."""
        if self._auth is None or user.id is None:
            return
        if not messagebox.askyesno(
            "Suppression",
            f"Supprimer définitivement l'utilisateur « {user.username} » ?",
        ):
            return
        try:
            self._auth.delete_user(user.id)
        except ValueError as exc:
            messagebox.showerror("Suppression", str(exc))
            return
        self._refresh_users()

    # ------------------------------------------------------------------ #
    # Vue : Journal
    # ------------------------------------------------------------------ #
    def _view_journal(self) -> None:
        """Affiche le journal des actions enregistrées en base."""
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(
            frame, text="Journal des actions",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))
        scroll = ctk.CTkScrollableFrame(frame, fg_color="transparent")
        scroll.grid(row=1, column=0, sticky="nsew")
        for entry in self._db.list_logs(300):
            line = ctk.CTkFrame(scroll, fg_color=CARD_BG, corner_radius=8)
            line.pack(fill="x", pady=2)
            color = {
                "ERROR": "#E63946", "WARNING": "#F4A261", "SUCCESS": "#43AA8B",
            }.get(entry.level, "#457B9D")
            ctk.CTkLabel(
                line, text=entry.action, width=90, text_color=color,
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", padx=8, pady=6)
            ctk.CTkLabel(
                line, text=entry.created_at[:19].replace("T", " "), width=150,
                text_color="#9A9AA0", font=ctk.CTkFont(size=11),
            ).pack(side="left")
            ctk.CTkLabel(
                line, text=entry.message, anchor="w", justify="left",
            ).pack(side="left", fill="x", expand=True, padx=8)

    # ------------------------------------------------------------------ #
    # Vue : Paramètres
    # ------------------------------------------------------------------ #
    def _view_parametres(self) -> None:
        """Affiche les paramètres modifiables de l'application."""
        frame = ctk.CTkScrollableFrame(self._content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(
            frame, text="Paramètres", font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(anchor="w", pady=(0, 6))
        ctk.CTkLabel(
            frame,
            text="Personnalisez l'apparence, le stockage et la connexion au serveur BOVO.",
            text_color="#9A9AA0", anchor="w",
        ).pack(anchor="w", pady=(0, 18))

        # --------- Apparence --------- #
        card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=14)
        card.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            card, text="Apparence",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(16, 6))

        theme_row = ctk.CTkFrame(card, fg_color="transparent")
        theme_row.pack(fill="x", padx=20, pady=(4, 12))
        ctk.CTkLabel(theme_row, text="Thème d'apparence", width=200, anchor="w").pack(
            side="left"
        )
        theme_var = ctk.StringVar(value=self._settings.theme)
        ctk.CTkOptionMenu(
            theme_row, values=["dark", "light", "system"], variable=theme_var,
            command=self._change_theme, fg_color=ACCENT, button_color=ACCENT_HOVER,
        ).pack(side="left")

        autosave_row = ctk.CTkFrame(card, fg_color="transparent")
        autosave_row.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkLabel(
            autosave_row, text="Sauvegarde automatique", width=200, anchor="w",
        ).pack(side="left")
        autosave_var = ctk.BooleanVar(value=self._settings.auto_save)
        ctk.CTkSwitch(
            autosave_row, text="", variable=autosave_var,
            command=lambda: self._settings.set("auto_save", autosave_var.get()),
            progress_color=ACCENT,
        ).pack(side="left")

        # --------- Connexion serveur --------- #
        server_card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=14)
        server_card.pack(fill="x", pady=(0, 14))
        ctk.CTkLabel(
            server_card, text="Connexion au serveur",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(16, 6))
        current_url = self._settings.server_url or "Non configuré"
        ctk.CTkLabel(
            server_card,
            text=f"🌐  URL actuelle : {current_url}",
            anchor="w", text_color="#B7B8BE",
        ).pack(anchor="w", padx=20, pady=(0, 4))
        ctk.CTkLabel(
            server_card,
            text=("L'URL est stockée localement sur ce poste et n'est plus "
                  "demandée au démarrage tant qu'elle reste valide."),
            anchor="w", text_color="#7A7A80",
            font=ctk.CTkFont(size=11), wraplength=640, justify="left",
        ).pack(anchor="w", padx=20, pady=(0, 10))
        ctk.CTkButton(
            server_card, text="🔧  Reconfigurer le serveur",
            fg_color="#457B9D", hover_color="#35617D", height=38,
            command=self._reconfigure_server,
        ).pack(anchor="w", padx=20, pady=(0, 16))

        # --------- Emplacements --------- #
        folders = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=14)
        folders.pack(fill="x")
        ctk.CTkLabel(
            folders, text="Emplacements",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(16, 6))
        ctk.CTkLabel(
            folders, text=f"📁  Dossier PDF : {self._settings.pdf_folder}",
            anchor="w", text_color="#B7B8BE",
        ).pack(anchor="w", padx=20)
        ctk.CTkLabel(
            folders, text=f"📤  Dossier export : {self._settings.export_folder}",
            anchor="w", text_color="#B7B8BE",
        ).pack(anchor="w", padx=20, pady=(4, 0))
        ctk.CTkLabel(
            folders, text=f"🗄️  Base de données : {self._db.path}",
            anchor="w", text_color="#B7B8BE",
        ).pack(anchor="w", padx=20, pady=(4, 16))

    def _reconfigure_server(self) -> None:
        """Ouvre le dialogue de configuration du serveur (depuis Paramètres)."""
        from app.server_config_dialog import ServerConfigDialog

        def _after_save() -> None:
            new_url = self._settings.server_url
            if self._client is not None and new_url:
                self._client._base_url = new_url.rstrip("/")  # noqa: SLF001
            messagebox.showinfo(
                "Serveur mis à jour",
                f"L'URL du serveur a été enregistrée :\n{new_url}\n\n"
                "Elle sera utilisée dès la prochaine connexion.",
            )
            self._show_view("parametres")

        ServerConfigDialog(
            self, self._settings,
            on_success=_after_save,
            on_cancel=lambda: None,
        )

    def _change_theme(self, theme: str) -> None:
        """Applique et persiste un nouveau thème."""
        ctk.set_appearance_mode(theme)
        self._settings.set("theme", theme)

    # ------------------------------------------------------------------ #
    # Cycle de vie
    # ------------------------------------------------------------------ #
    def on_close(self) -> None:
        """Sauvegarde la géométrie et ferme proprement l'application."""
        self._settings.set("window_width", self.winfo_width())
        self._settings.set("window_height", self.winfo_height())
        log_action(self._db, LogAction.CLOSE, "Fermeture de l'application.")
        self._db.close()
        self.destroy()

    def reveal(self) -> None:
        """Affiche la fenêtre principale (après le splash)."""
        self.deiconify()
        self.lift()
        self.focus_force()
