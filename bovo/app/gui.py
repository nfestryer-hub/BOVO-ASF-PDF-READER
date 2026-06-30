"""Interface graphique CustomTkinter de BOVO Planning Manager.

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
from app.calendar import STATUT_COLORS, WEEKDAY_NAMES_FR, CalendarModel, DayCell
from app.database import Database
from app.exporter import Exporter
from app.inspections import FieldSpec, InspectionService
from app.logger import LogAction, get_logger, log_action
from app.models import Intervention, StatutIntervention
from app.planner import ImportResult, Planner
from app.settings import Settings
from app.utils import (
    ASSETS_DIR,
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
            self, text="BOVO Planning Manager",
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
        service: InspectionService,
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
        self.geometry("560x680")
        self.configure(fg_color=SURFACE)
        self.grab_set()

        head = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0)
        head.pack(fill="x")
        ctk.CTkLabel(
            head, text=f"{verb} une entrée — {label}",
            font=ctk.CTkFont(size=18, weight="bold"), text_color="white",
        ).pack(padx=20, pady=16, anchor="w")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=10)

        existing = service.get_row(sheet, row_id) if row_id is not None else {}
        for field in service.form_fields(sheet):
            self._build_field(body, field, (existing or {}).get(field.column, ""))

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


class BovoApp(ctk.CTk):
    """Fenêtre principale du logiciel."""

    def __init__(self, database: Database, settings: Settings) -> None:
        super().__init__()
        self._db = database
        self._settings = settings
        self._planner = Planner(database)
        self._exporter = Exporter(database)
        self._inspections = InspectionService(database)
        self._calendar_model = CalendarModel()
        self._progress_queue: queue.Queue[tuple] = queue.Queue()

        today = date.today()
        self._cal_year = today.year
        self._cal_month = today.month

        self.title("BOVO Planning Manager")
        width, height = settings.window_size
        self.geometry(f"{width}x{height}")
        self.minsize(1100, 720)
        self.withdraw()  # masquée tant que le splash s'affiche.

        self._build_layout()
        self._show_view("accueil")

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
            image = ctk.CTkImage(Image.open(logo_path), size=(150, 150))
            ctk.CTkLabel(sidebar, image=image, text="").pack(pady=(24, 4))
        ctk.CTkLabel(
            sidebar, text="Planning Manager",
            font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(pady=(0, 20))

        self._nav_buttons: dict[str, ctk.CTkButton] = {}
        nav_items = [
            ("accueil", "🏠  Accueil"),
            ("calendrier", "📅  Calendrier"),
            ("interventions", "🔍  Interventions"),
            ("inspections", "🧰  Inspections ASF"),
            ("import", "⬆️  Importer PDF"),
            ("journal", "📝  Journal"),
            ("parametres", "⚙️  Paramètres"),
        ]
        for key, label in nav_items:
            btn = ctk.CTkButton(
                sidebar, text=label, anchor="w", height=44,
                fg_color="transparent", text_color=("black", "white"),
                hover_color=ACCENT, corner_radius=8,
                command=lambda k=key: self._show_view(k),
            )
            btn.pack(fill="x", padx=16, pady=4)
            self._nav_buttons[key] = btn

        ctk.CTkLabel(
            sidebar, text=f"v{__version__} · {__author__}",
            font=ctk.CTkFont(size=11), text_color="#7A7A80",
        ).pack(side="bottom", pady=16)

        self._content = ctk.CTkFrame(self, fg_color="transparent")
        self._content.grid(row=0, column=1, sticky="nsew", padx=24, pady=24)
        self._content.grid_columnconfigure(0, weight=1)
        self._content.grid_rowconfigure(0, weight=1)

    def _clear_content(self) -> None:
        """Vide la zone de contenu avant d'afficher une nouvelle vue."""
        for widget in self._content.winfo_children():
            widget.destroy()

    def _show_view(self, key: str) -> None:
        """Affiche la vue demandée et met en surbrillance l'onglet actif."""
        for nav_key, btn in self._nav_buttons.items():
            btn.configure(fg_color=ACCENT if nav_key == key else "transparent")
        self._clear_content()
        builder = {
            "accueil": self._view_accueil,
            "calendrier": self._view_calendrier,
            "interventions": self._view_interventions,
            "inspections": self._view_inspections,
            "import": self._view_import,
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
            frame, text=f"Bonjour {get_system_username()} 👋",
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
        interventions = self._db.list_interventions_between(iso, iso)
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
        frame.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(
            header, text="Inspections ASF (ITV)",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(side="left")
        ctk.CTkButton(
            header, text="📊  Importer le classeur Excel", fg_color="#43AA8B",
            hover_color="#369072", command=self._import_workbook,
        ).pack(side="right")

        tabview = ctk.CTkTabview(frame, fg_color=CARD_BG)
        tabview.grid(row=1, column=0, sticky="nsew")

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
            toolbar, text="➕  Ajouter", width=120, fg_color=ACCENT,
            hover_color=ACCENT_HOVER,
            command=lambda sh=sheet: self._open_row_form(sh, None),
        ).pack(side="right", padx=4)

        table = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        table.grid(row=1, column=0, sticky="nsew")
        self._insp_tables[sheet] = table

    def _refresh_module(self, sheet: str) -> None:
        """Recharge la table d'un module ASF selon la recherche."""
        table = self._insp_tables[sheet]
        for widget in table.winfo_children():
            widget.destroy()
        columns = self._inspections.list_columns(sheet)
        rows = self._inspections.list_rows(sheet, self._insp_search[sheet].get().strip())

        head = ctk.CTkFrame(table, fg_color=CARD_BG, corner_radius=8)
        head.pack(fill="x", pady=(0, 4))
        for _col, label in columns:
            ctk.CTkLabel(
                head, text=label, width=150, anchor="w",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).pack(side="left", padx=6, pady=8)
        ctk.CTkLabel(head, text="", width=80).pack(side="left")

        if not rows:
            ctk.CTkLabel(
                table, text="Aucune donnée. Cliquez « Ajouter » ou importez le classeur.",
                text_color="#9A9AA0",
            ).pack(anchor="w", pady=20)
            return

        for row in rows:
            self._module_row(sheet, row, columns)

    def _module_row(
        self, sheet: str, row: dict[str, str], columns: list[tuple[str, str]]
    ) -> None:
        """Construit une ligne de table de module (éditable + suppression)."""
        container = ctk.CTkFrame(
            self._insp_tables[sheet], fg_color=SURFACE, height=40, corner_radius=8
        )
        container.pack(fill="x", pady=2)
        row_id = int(row["id"])
        handler = lambda _e=None, sh=sheet, rid=row_id: self._open_row_form(sh, rid)  # noqa: E731
        container.bind("<Button-1>", handler)
        for col, _label in columns:
            value = row.get(col, "") or "—"
            if col == "date":
                value = format_date_fr(parse_iso_date(row.get(col))) or value
            label = ctk.CTkLabel(
                container, text=str(value)[:24], width=150, anchor="w",
                font=ctk.CTkFont(size=12),
            )
            label.pack(side="left", padx=6, pady=8)
            label.bind("<Button-1>", handler)
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
        frame = ctk.CTkFrame(self._content, fg_color="transparent")
        frame.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(
            frame, text="Paramètres", font=ctk.CTkFont(size=24, weight="bold"),
        ).pack(anchor="w", pady=(0, 20))

        card = ctk.CTkFrame(frame, fg_color=CARD_BG, corner_radius=14)
        card.pack(fill="x")

        theme_row = ctk.CTkFrame(card, fg_color="transparent")
        theme_row.pack(fill="x", padx=20, pady=16)
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

        folders = ctk.CTkFrame(card, fg_color="transparent")
        folders.pack(fill="x", padx=20, pady=(0, 16))
        ctk.CTkLabel(
            folders, text=f"Dossier PDF : {self._settings.pdf_folder}",
            anchor="w", text_color="#9A9AA0",
        ).pack(anchor="w")
        ctk.CTkLabel(
            folders, text=f"Dossier export : {self._settings.export_folder}",
            anchor="w", text_color="#9A9AA0",
        ).pack(anchor="w")
        ctk.CTkLabel(
            folders, text=f"Base de données : {self._db.path}",
            anchor="w", text_color="#9A9AA0",
        ).pack(anchor="w")

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
