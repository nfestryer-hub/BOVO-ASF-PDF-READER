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
