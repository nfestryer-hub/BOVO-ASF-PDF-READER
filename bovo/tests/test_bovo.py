"""Tests automatisés de la logique métier (parser de dates, parsing PDF,
base SQLite, planner et calendrier). Exécuter avec ``pytest`` depuis /app/bovo.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.calendar import CalendarModel  # noqa: E402
from app.database import Database  # noqa: E402
from app.models import Intervention, StatutIntervention  # noqa: E402
from app.parser_pdf import DateParser, PdfParser  # noqa: E402
from app.planner import Planner  # noqa: E402

SAMPLE_PDF = ROOT / "sample" / "Listing_Ouvrages_BOVO.pdf"
SAMPLE_XLSX = ROOT / "sample" / "Classeur_ASF.xlsx"


@pytest.fixture()
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("15/06/2026", [date(2026, 6, 15)]),
        ("15 et 16/07/2026", [date(2026, 7, 15), date(2026, 7, 16)]),
        ("23 au 26/11/2026", [date(2026, 11, d) for d in (23, 24, 25, 26)]),
        ("27-28-29-30/07/2026", [date(2026, 7, d) for d in (27, 28, 29, 30)]),
        ("29-30/06/2026", [date(2026, 6, 29), date(2026, 6, 30)]),
        ("nuits 22 et 23/06/2026", [date(2026, 6, 22), date(2026, 6, 23)]),
        ("28 au 30/07/2026", [date(2026, 7, 28), date(2026, 7, 29), date(2026, 7, 30)]),
        ("", []),
    ],
)
def test_date_parser(raw: str, expected: list[date]) -> None:
    assert DateParser().parse(raw) == expected


def test_upsert_dedup_by_ouvrage(db: Database) -> None:
    iv = Intervention(ouvrage="43854", objet="CANIVEAU", autoroute="A62")
    _, created = db.upsert_intervention(iv)
    assert created is True
    iv2 = Intervention(ouvrage="43854", objet="CANIVEAU", autoroute="A62", secteur="X")
    _, created2 = db.upsert_intervention(iv2)
    assert created2 is False
    assert len(db.list_interventions()) == 1
    assert db.get_intervention_by_ouvrage("43854").secteur == "X"


def test_calendar_projects_multiday(db: Database) -> None:
    iv = Intervention(
        ouvrage="1",
        date_debut=date(2026, 7, 28),
        date_fin=date(2026, 7, 30),
        statut=StatutIntervention.PLANIFIEE,
    )
    weeks = CalendarModel().build_month(2026, 7, [iv])
    covered = [c for week in weeks for c in week if c.count > 0]
    days = {c.day_date.day for c in covered}
    assert {28, 29, 30}.issubset(days)


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="PDF d'exemple absent")
def test_parse_real_pdf(db: Database) -> None:
    parser = PdfParser()
    parsed = parser.parse_file(SAMPLE_PDF)
    assert len(parsed) > 10
    assert any(p.autoroute == "A62" for p in parsed)
    assert any(p.dates for p in parsed)


@pytest.mark.skipif(not SAMPLE_PDF.exists(), reason="PDF d'exemple absent")
def test_planner_import_real_pdf(db: Database) -> None:
    planner = Planner(db)
    result = planner.import_pdf(SAMPLE_PDF)
    assert result.files_processed == 1
    assert result.total_interventions > 10
    stats = planner.get_statistics()
    assert stats["total"] == result.total_interventions
    assert stats["pdfs"] == 1


def test_inspection_crud_and_referentiel(db: Database) -> None:
    from app.inspections import InspectionService

    svc = InspectionService(db)
    assert "A62" in svc.referentiel("autoroutes")
    new_id = svc.save_row(
        "inspections",
        {"n_inspection": "1", "date": "2026-07-15", "autoroute": "A62",
         "ml_inspectes": "120", "nb_regards": "4", "heures_totales": "2"},
    )
    assert new_id > 0
    rows = svc.list_rows("inspections")
    assert len(rows) == 1
    kpis = svc.kpis()
    assert kpis["nb_inspections"] == "1"
    assert kpis["ml_h"] == "60.0"
    svc.delete_row("inspections", new_id)
    assert svc.list_rows("inspections") == []


def test_rapport_marks_intervention_done(db: Database) -> None:
    from app.inspections import InspectionService
    from app.models import Intervention, StatutIntervention

    db.upsert_intervention(Intervention(ouvrage="43854", objet="CANIVEAU"))
    svc = InspectionService(db)
    svc.save_row("rapports", {"date": "2026-06-22", "identifiant": "43854"})
    updated = db.get_intervention_by_ouvrage("43854")
    assert updated is not None
    assert updated.statut is StatutIntervention.TERMINEE


@pytest.mark.skipif(not SAMPLE_XLSX.exists(), reason="Classeur d'exemple absent")
def test_import_workbook_real(db: Database) -> None:
    from app.inspections import InspectionService

    svc = InspectionService(db)
    summary = svc.import_workbook(SAMPLE_XLSX)
    assert summary["inspections"] == 8
    assert summary["rapports"] == 8
    assert svc.kpis()["regards"] == "56"
