"""Tests V1.2 — corrections signalées sur la branche V14 :

* Calendrier : les **week-ends** (samedi + dimanche) sont exclus de
  l'index — un ouvrage lu-ma-me-je-ve-sa-di-lu doit apparaître seulement
  sur les 5 jours ouvrés Lundi-Vendredi.
* Export PDF Inspections/Rapports : la table ne doit pas être vide
  (les valeurs doivent apparaître dans le PDF).
* Version unifiée (source unique dans ``app.version``).
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_calendar_excludes_weekends() -> None:
    """Un ouvrage sur Lu-Di ne doit être indexé QUE sur les jours ouvrés."""
    from app.calendar import CalendarModel
    from app.models import Intervention, StatutIntervention

    # Semaine du lundi 2 sept au dimanche 8 sept 2026.
    iv = Intervention(
        ouvrage="TEST", objet="Semaine complète",
        date_debut=date(2026, 9, 7), date_fin=date(2026, 9, 13),
        statut=StatutIntervention.PLANIFIEE,
    )
    model = CalendarModel()
    index = model._index_by_day([iv])
    # 7=Lu, 8=Ma, 9=Me, 10=Je, 11=Ve, 12=Sa, 13=Di → 5 jours ouvrés.
    covered = sorted(index.keys())
    assert covered == [
        date(2026, 9, 7), date(2026, 9, 8), date(2026, 9, 9),
        date(2026, 9, 10), date(2026, 9, 11),
    ]
    assert date(2026, 9, 12) not in index  # samedi exclu
    assert date(2026, 9, 13) not in index  # dimanche exclu


def test_calendar_04_to_30_septembre_uses_only_weekdays() -> None:
    """Cas d'usage terrain : 04/09/26 au 30/09/26 = 20 jours ouvrés
    (pas 27 jours calendaires — les week-ends sont exclus)."""
    from app.calendar import CalendarModel
    from app.models import Intervention, StatutIntervention

    iv = Intervention(
        ouvrage="43854", objet="Chantier long",
        date_debut=date(2026, 9, 4), date_fin=date(2026, 9, 30),
        statut=StatutIntervention.PLANIFIEE,
    )
    index = CalendarModel()._index_by_day([iv])
    # Sept 2026 : 04=Ve, 05=Sa, 06=Di, … 30=Me.
    # Compte des jours ouvrés du 04 au 30 : 4, 7-11, 14-18, 21-25, 28-30
    # = 1 + 5 + 5 + 5 + 3 = 19 jours ouvrés.
    assert len(index) == 19
    # Aucun samedi/dimanche dans l'index.
    for d in index:
        assert d.weekday() < 5, f"{d} est un jour de week-end !"


def test_pdf_export_inspections_shows_data(tmp_path: Path) -> None:
    """Régression du bug V14 : l'export PDF ne doit pas être vide."""
    from app.database import Database
    from app.inspections import InspectionService

    db = Database(tmp_path / "t.db")
    try:
        svc = InspectionService(db)
        svc.save_row("inspections", {
            "n_inspection": "42", "date": "2026-09-04",
            "autoroute": "A62", "secteur": "Garonne",
            "ml_inspectes": "320", "operateur": "Hugo D.",
        })
        dest = tmp_path / "insp.pdf"
        svc.export_pdf("inspections", dest)
        doc = fitz.open(str(dest))
        text = doc[0].get_text().replace("\n", " ")
        doc.close()
        # Bug historique : PDF ne contenait QUE le titre et le pied de page.
        # Après correction, les valeurs doivent apparaître.
        assert "42" in text
        assert "A62" in text
        assert "Hugo" in text
        # En-têtes visibles aussi.
        assert "Inspection" in text
        assert "Autoroute" in text
    finally:
        db.close()


def test_pdf_export_rapports_shows_data(tmp_path: Path) -> None:
    """Régression : l'export PDF Rapports d'inspection ASF ne doit pas être vide."""
    from app.database import Database
    from app.inspections import InspectionService

    db = Database(tmp_path / "t.db")
    try:
        svc = InspectionService(db)
        svc.save_row("rapports", {
            "date": "2026-09-04", "identifiant": "43854",
            "prestataire": "BOVO", "inspecteur": "Hugo D.",
            "autoroute": "A62", "secteur": "Garonne",
        })
        dest = tmp_path / "rap.pdf"
        svc.export_pdf("rapports", dest)
        doc = fitz.open(str(dest))
        text = doc[0].get_text().replace("\n", " ")
        doc.close()
        assert "43854" in text
        assert "BOVO" in text
        assert "A62" in text
    finally:
        db.close()


def test_version_is_unified_from_version_module() -> None:
    """``__version__`` de ``app.__init__`` provient de ``app.version``."""
    from app import __version__
    from app.version import __version__ as version_module

    assert __version__ == version_module
