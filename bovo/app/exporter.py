"""Export des interventions vers Excel, CSV, JSON et PDF.

Module métier séparé du GUI. L'export Excel s'appuie sur ``openpyxl`` et
l'export PDF sur PyMuPDF (fitz), déjà imposés par le projet.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime
from pathlib import Path

import fitz  # PyMuPDF
from openpyxl import Workbook

from app.database import Database
from app.logger import LogAction, get_logger, log_action
from app.models import Intervention
from app.utils import format_date_fr

logger = get_logger("exporter")

_COLUMNS: tuple[tuple[str, str], ...] = (
    ("ouvrage", "Ouvrage"),
    ("objet", "Objet"),
    ("autoroute", "Autoroute"),
    ("secteur", "Secteur"),
    ("pr_debut", "PR début"),
    ("pr_fin", "PR fin"),
    ("sens", "Sens"),
    ("longueur", "Longueur"),
    ("diametre", "Diamètre"),
    ("type_ouvrage", "Type d'ouvrage"),
    ("date_debut", "Date début"),
    ("date_fin", "Date fin"),
    ("statut", "Statut"),
    ("commentaire", "Commentaire"),
)


def _row_values(iv: Intervention) -> list[str]:
    """Sérialise une intervention en liste de chaînes pour export tabulaire."""
    values: list[str] = []
    for attr, _ in _COLUMNS:
        raw = getattr(iv, attr)
        if isinstance(raw, date):
            values.append(format_date_fr(raw))
        elif hasattr(raw, "value"):
            values.append(str(raw.value))
        else:
            values.append("" if raw is None else str(raw))
    return values


class Exporter:
    """Fournit les exports multi-formats des interventions."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def to_excel(self, interventions: list[Intervention], destination: Path) -> Path:
        """Exporte les interventions au format Excel (.xlsx)."""
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Interventions"
        sheet.append([label for _, label in _COLUMNS])
        for iv in interventions:
            sheet.append(_row_values(iv))
        destination.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(str(destination))
        log_action(self._db, LogAction.EXPORT, f"Export Excel : {destination.name}")
        return destination

    def to_csv(self, interventions: list[Intervention], destination: Path) -> Path:
        """Exporte les interventions au format CSV (séparateur ';')."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow([label for _, label in _COLUMNS])
            for iv in interventions:
                writer.writerow(_row_values(iv))
        log_action(self._db, LogAction.EXPORT, f"Export CSV : {destination.name}")
        return destination

    def to_json(self, interventions: list[Intervention], destination: Path) -> Path:
        """Exporte les interventions au format JSON."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": datetime.now(UTC).isoformat(),
            "count": len(interventions),
            "interventions": [iv.to_row() for iv in interventions],
        }
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log_action(self._db, LogAction.EXPORT, f"Export JSON : {destination.name}")
        return destination

    def to_pdf(self, interventions: list[Intervention], destination: Path) -> Path:
        """Exporte un planning lisible au format PDF via PyMuPDF."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open()
        page = document.new_page()
        margin, top = 40, 60
        page.insert_text(
            (margin, 40),
            f"BOVO Planning Manager — Export du {format_date_fr(date.today())}",
            fontsize=14,
        )
        line_height = 16
        y = top
        for iv in interventions:
            if y > page.rect.height - margin:
                page = document.new_page()
                y = top
            text = (
                f"{iv.ouvrage} | {iv.objet} | {iv.autoroute} | "
                f"{format_date_fr(iv.date_debut)}→{format_date_fr(iv.date_fin)} | "
                f"{iv.statut.value}"
            )
            page.insert_text((margin, y), text[:120], fontsize=9)
            y += line_height
        document.save(str(destination))
        document.close()
        log_action(self._db, LogAction.EXPORT, f"Export PDF : {destination.name}")
        return destination

    def table_to_pdf(
        self,
        title: str,
        headers: list[str],
        rows: list[list[str]],
        destination: Path,
    ) -> Path:
        """Exporte un tableau générique (mode tableur) au format PDF paysage.

        Args:
            title: Titre imprimé en haut de la première page.
            headers: Libellés des colonnes.
            rows: Contenu du tableau (chaque ligne = liste alignée aux headers).
            destination: Chemin du PDF cible.

        Returns:
            Le chemin du PDF généré.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open()
        page_width, page_height = 842.0, 595.0  # A4 paysage
        margin_x, margin_y = 30.0, 40.0
        header_h = 22.0
        row_h = 18.0
        usable_w = page_width - 2 * margin_x
        n_cols = max(len(headers), 1)
        col_w = usable_w / n_cols

        def new_page() -> tuple[fitz.Page, float]:
            page = document.new_page(width=page_width, height=page_height)
            page.insert_text(
                (margin_x, margin_y - 12),
                f"{title} — {format_date_fr(date.today())}",
                fontsize=13,
            )
            _draw_row(page, margin_y, headers, header_h, filled=True)
            return page, margin_y + header_h

        def _draw_row(
            page: fitz.Page, y: float, cells: list[str], height: float, *, filled: bool
        ) -> None:
            for idx, value in enumerate(cells):
                rect = fitz.Rect(
                    margin_x + idx * col_w, y,
                    margin_x + (idx + 1) * col_w, y + height,
                )
                if filled:
                    page.draw_rect(rect, color=(0.1, 0.1, 0.1), fill=(0.9, 0.23, 0.27), width=0.5)
                    color = (1.0, 1.0, 1.0)
                else:
                    page.draw_rect(rect, color=(0.6, 0.6, 0.6), width=0.4)
                    color = (0.05, 0.05, 0.05)
                text = (value or "").replace("\n", " ")
                max_chars = max(int(col_w / 4.6), 6)
                if len(text) > max_chars:
                    text = text[: max_chars - 1] + "…"
                page.insert_text(
                    (rect.x0 + 4, rect.y0 + height - 6),
                    text, fontsize=8, color=color,
                )

        page, y = new_page()
        for row in rows:
            if y + row_h > page_height - margin_y:
                page, y = new_page()
            padded = list(row) + [""] * max(0, n_cols - len(row))
            _draw_row(page, y, padded[:n_cols], row_h, filled=False)
            y += row_h

        page.insert_text(
            (margin_x, page_height - 15),
            f"{len(rows)} ligne(s) — Développé par HENRI Dylan",
            fontsize=8, color=(0.4, 0.4, 0.4),
        )
        document.save(str(destination))
        document.close()
        log_action(
            self._db, LogAction.EXPORT,
            f"Export PDF (tableur) : {destination.name} — {len(rows)} ligne(s)",
        )
        return destination
