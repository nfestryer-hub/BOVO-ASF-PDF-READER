"""Tests de régression — Export PDF tableur (inspections, incidents, matériel).

Bug historique : le tableau était rendu vide (cellules et en-têtes sans
texte) car :meth:`fitz.Page.insert_textbox` retournait une valeur négative
quand la hauteur de cellule était trop juste par rapport à la police.

Ce test garantit que les valeurs métier apparaissent bien dans le PDF.
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import Database  # noqa: E402
from app.inspections import InspectionService  # noqa: E402


def _extract_text(pdf_path: Path) -> str:
    """Concatène le texte extrait de toutes les pages du PDF."""
    doc = fitz.open(str(pdf_path))
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def test_pdf_export_inspections_contains_values(tmp_path: Path) -> None:
    """L'export PDF du module Inspections doit contenir les valeurs saisies."""
    db = Database(tmp_path / "t.db")
    try:
        svc = InspectionService(db)
        svc.save_row("inspections", {
            "n_inspection": "42", "date": "2026-06-22",
            "autoroute": "A62", "secteur": "Garonne",
            "ml_inspectes": "320", "operateur": "Hugo D.",
        })
        dest = tmp_path / "inspections.pdf"
        svc.export_pdf("inspections", dest)
        assert dest.exists()
        text = _extract_text(dest)
        # En-têtes de colonnes doivent apparaître.
        assert "N° Inspection" in text
        assert "Autoroute" in text
        # Valeurs doivent apparaître.
        assert "42" in text
        assert "A62" in text
        assert "Garonne" in text
        assert "Hugo D." in text
    finally:
        db.close()


def test_pdf_export_incidents_contains_values(tmp_path: Path) -> None:
    """L'export PDF du module Incidents doit contenir les valeurs saisies."""
    db = Database(tmp_path / "t.db")
    try:
        svc = InspectionService(db)
        svc.save_row("incidents", {
            "date": "2026-06-23", "autoroute": "A61", "pk": "15+200",
            "type_incident": "Effondrement",
            "impact": "Voie fermée",
        })
        dest = tmp_path / "incidents.pdf"
        svc.export_pdf("incidents", dest)
        text = _extract_text(dest)
        assert "Type Incident" in text
        assert "A61" in text
        assert "Effondrement" in text
        assert "15+200" in text
    finally:
        db.close()


def test_pdf_export_materiel_contains_values(tmp_path: Path) -> None:
    """L'export PDF du module Matériel doit contenir les valeurs saisies."""
    db = Database(tmp_path / "t.db")
    try:
        svc = InspectionService(db)
        svc.save_row("materiel", {
            "date": "2026-06-24", "camera": "IBAK Orpheus 2",
            "vehicule": "Sprinter 41", "panne": "Aucune",
        })
        dest = tmp_path / "materiel.pdf"
        svc.export_pdf("materiel", dest)
        text = _extract_text(dest)
        assert "Caméra" in text
        assert "IBAK" in text  # peut être coupé par retour ligne
        assert "Sprinter" in text
        assert "Aucune" in text
    finally:
        db.close()


def test_pdf_export_empty_module_still_renders(tmp_path: Path) -> None:
    """Un module vide doit produire un PDF valide (headers + '0 lignes')."""
    db = Database(tmp_path / "t.db")
    try:
        svc = InspectionService(db)
        dest = tmp_path / "empty.pdf"
        svc.export_pdf("inspections", dest)
        text = _extract_text(dest)
        assert "0 ligne" in text
        # Les en-têtes doivent être présents même sans données.
        assert "N° Inspection" in text
    finally:
        db.close()
