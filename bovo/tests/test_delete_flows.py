"""Tests V4 — Suppression des interventions et des rapports d'inspection.

Vérifie que :
* :meth:`Planner.delete` supprime bien l'intervention en base.
* :meth:`InspectionService.delete_row` supprime bien la ligne d'un module ASF.
* Les tables sont vides après suppression totale.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import Database  # noqa: E402
from app.inspections import InspectionService  # noqa: E402
from app.models import Intervention, StatutIntervention  # noqa: E402
from app.planner import Planner  # noqa: E402


def test_delete_intervention_removes_from_db(tmp_path: Path) -> None:
    """``Planner.delete(id)`` doit supprimer l'intervention de la base."""
    db = Database(tmp_path / "t.db")
    try:
        planner = Planner(db)
        iv, _ = db.upsert_intervention(Intervention(
            ouvrage="43854", objet="Test suppression",
            date_debut=date.today(), date_fin=date.today(),
            statut=StatutIntervention.PLANIFIEE,
        ))
        assert iv.id is not None
        assert db.get_intervention_by_ouvrage("43854") is not None

        planner.delete(iv.id)

        assert db.get_intervention_by_ouvrage("43854") is None
        assert not any(
            i.ouvrage == "43854" for i in db.list_interventions()
        )
    finally:
        db.close()


def test_delete_rapport_row_removes_from_module(tmp_path: Path) -> None:
    """``InspectionService.delete_row('rapports', id)`` doit retirer la ligne."""
    db = Database(tmp_path / "t.db")
    try:
        svc = InspectionService(db)
        rid = svc.save_row("rapports", {
            "date": "2026-06-22",
            "identifiant": "43854",
            "prestataire": "BOVO & FILS",
            "inspecteur": "Hugo D.",
            "type_ouvrage": "Caniveau",
        })
        assert svc.get_row("rapports", rid) is not None
        assert len(svc.list_rows("rapports")) == 1

        svc.delete_row("rapports", rid)

        assert svc.get_row("rapports", rid) is None
        assert svc.list_rows("rapports") == []
    finally:
        db.close()


def test_delete_rapport_does_not_affect_other_modules(tmp_path: Path) -> None:
    """La suppression d'un rapport ne doit pas toucher les autres modules."""
    db = Database(tmp_path / "t.db")
    try:
        svc = InspectionService(db)
        rid_rapport = svc.save_row("rapports", {
            "identifiant": "R1", "type_ouvrage": "Caniveau",
        })
        rid_incident = svc.save_row("incidents", {
            "date": "2026-06-22", "autoroute": "A62",
        })

        svc.delete_row("rapports", rid_rapport)

        assert svc.get_row("rapports", rid_rapport) is None
        # L'incident est intact.
        assert svc.get_row("incidents", rid_incident) is not None
    finally:
        db.close()
