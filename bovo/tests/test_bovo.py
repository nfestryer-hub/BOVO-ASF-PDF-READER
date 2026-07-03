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


@pytest.mark.parametrize(
    ("depart", "arrivee", "expected"),
    [
        ("12+000", "12+345", "345"),
        ("12.000", "12.345", "345"),
        ("12,000", "12,345", "345"),
        ("12", "13", "1000"),
        ("12345", "13000", "655"),
        ("PR 12+500", "PR 13+250", "750"),
        ("", "12+500", ""),
        ("abc", "def", ""),
    ],
)
def test_compute_ml_inspectes(depart: str, arrivee: str, expected: str) -> None:
    from app.utils import compute_ml_inspectes

    assert compute_ml_inspectes(depart, arrivee) == expected


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("08:00", "16:00", "8"),
        ("08:30", "17:15", "8.75"),
        ("22:00", "02:00", "4"),  # passage minuit
        ("8h", "10h30", "2.5"),
        ("", "10:00", ""),
        ("nope", "10:00", ""),
    ],
)
def test_compute_heures_totales(start: str, end: str, expected: str) -> None:
    from app.utils import compute_heures_totales

    assert compute_heures_totales(start, end) == expected


def test_prefill_rapport_from_latest_inspection(db: Database) -> None:
    from app.inspections import InspectionService

    svc = InspectionService(db)
    assert svc.prefill_rapport() == {"prestataire": "BOVO & FILS"}
    svc.save_row(
        "inspections",
        {
            "n_inspection": "42", "date": "2026-07-20", "autoroute": "A62",
            "secteur": "Garonne", "operateur": "Hugo D.",
        },
    )
    prefill = svc.prefill_rapport()
    assert prefill["date"] == "2026-07-20"
    assert prefill["n_inspection"] == "42"
    assert prefill["autoroute"] == "A62"
    assert prefill["secteur"] == "Garonne"
    assert prefill["inspecteur"] == "Hugo D."
    assert prefill["prestataire"] == "BOVO & FILS"
    # Champs manuels absents.
    for col in ("identifiant", "photo", "description", "type_defaut"):
        assert col not in prefill


def test_export_pdf_module(tmp_path: Path, db: Database) -> None:
    from app.inspections import InspectionService

    svc = InspectionService(db)
    svc.save_row(
        "inspections",
        {"n_inspection": "1", "date": "2026-07-15", "autoroute": "A62",
         "secteur": "Garonne", "ml_inspectes": "300"},
    )
    destination = tmp_path / "export.pdf"
    result = svc.export_pdf("inspections", destination)
    assert result.exists()
    assert result.stat().st_size > 500  # PDF non vide


# ---------------------------------------------------------------------- #
# Authentification (bcrypt local, mono-poste)
# ---------------------------------------------------------------------- #
def test_auth_seed_default_users(db: Database) -> None:
    from app.auth import AuthService, Role

    svc = AuthService(db)
    users = svc.list_users()
    usernames = {u.username: u.role for u in users}
    assert usernames["Bovo"] is Role.ADMIN
    assert usernames["Dylan HENRI"] is Role.PLANIFICATEUR
    assert usernames["ASF"] is Role.CONSULTANT

    # Le seed est idempotent : un second appel ne recrée rien.
    assert svc.seed_default_users() == 0


def test_auth_login_success_and_failure(db: Database) -> None:
    from app.auth import AuthService

    svc = AuthService(db)
    user = svc.login("Bovo", "ibak23")
    assert user is not None
    assert svc.session.is_authenticated
    assert svc.session.can_edit()
    assert svc.session.can_view_planning()
    assert svc.session.can_manage_users()

    svc.logout()
    assert svc.login("Bovo", "wrong") is None
    assert not svc.session.is_authenticated


def test_auth_role_permissions(db: Database) -> None:
    from app.auth import AuthService, Role

    svc = AuthService(db)
    # Consultant : lecture seule stricte.
    svc.login("ASF", "asfmontauban!")
    assert not svc.session.can_edit()
    assert not svc.session.can_view_planning()
    assert not svc.session.can_manage_users()
    assert not svc.session.can_view_audit()

    # Planificateur (V1.2) : full sur planning + import, mais PAS d'audit,
    # PAS d'édition des inspections ASF (rapports en lecture seule),
    # PAS de gestion des users.
    svc.logout()
    svc.login("Dylan HENRI", "0811048re55Ol5!")
    assert svc.session.can_edit()
    assert svc.session.can_view_planning()
    assert svc.session.can_import_pdf()
    assert not svc.session.can_edit_inspections()  # ← nouveau V1.2
    assert not svc.session.can_manage_users()
    assert not svc.session.can_view_audit()  # ← retiré en V1.2

    # Admin : tout.
    svc.logout()
    svc.login("Bovo", "ibak23")
    assert svc.session.can_edit()
    assert svc.session.can_edit_inspections()
    assert svc.session.can_view_planning()
    assert svc.session.can_manage_users()
    assert svc.session.can_view_audit()

    # Inspecteur ITV : comme Admin mais sans audit/users.
    svc.logout()
    inspecteur = svc.create_user(
        "hugo", "S3cret!", Role.INSPECTEUR_ITV, "Hugo D.",
    )
    assert inspecteur.id is not None
    svc.login("hugo", "S3cret!")
    assert svc.session.can_edit()
    assert svc.session.can_edit_inspections()
    assert svc.session.can_view_planning()
    assert svc.session.can_import_pdf()
    assert not svc.session.can_manage_users()
    assert not svc.session.can_view_audit()


def test_auth_create_and_change_password(db: Database) -> None:
    from app.auth import AuthService, Role

    svc = AuthService(db)
    new_user = svc.create_user("test_user", "S3cret!", Role.PLANIFICATEUR, "Test")
    assert new_user.id is not None
    assert svc.login("test_user", "S3cret!") is not None
    svc.change_password(int(new_user.id), "N3wPass!")
    assert svc.login("test_user", "S3cret!") is None
    assert svc.login("test_user", "N3wPass!") is not None


# ---------------------------------------------------------------------- #
# Audit trail
# ---------------------------------------------------------------------- #
def test_audit_records_inspection_lifecycle(db: Database) -> None:
    from app.audit import AuditService
    from app.inspections import InspectionService

    audit = AuditService(db)
    audit.bind_session("Bovo", "Admin")
    svc = InspectionService(db, audit=audit)

    row_id = svc.save_row(
        "inspections",
        {"n_inspection": "42", "date": "2026-07-20", "autoroute": "A62"},
    )
    svc.save_row(
        "inspections",
        {"n_inspection": "42", "date": "2026-07-20", "autoroute": "A66"},
        row_id=row_id,
    )
    svc.delete_row("inspections", row_id)

    entries = audit.list_entries()
    actions = [e.action for e in entries]
    assert "create" in actions and "update" in actions and "delete" in actions
    update_entry = next(e for e in entries if e.action == "update")
    diff = dict((k, (b, a)) for k, b, a in update_entry.diff())
    assert diff["autoroute"] == ("A62", "A66")


def test_audit_intervention_status_change(db: Database) -> None:
    from app.audit import AuditService
    from app.models import Intervention, StatutIntervention
    from app.planner import Planner

    audit = AuditService(db)
    audit.bind_session("Dylan HENRI", "Planificateur")
    iv, _ = db.upsert_intervention(Intervention(ouvrage="99", objet="TEST"))
    planner = Planner(db, audit=audit)
    planner.set_statut(int(iv.id or 0), StatutIntervention.TERMINEE)

    entries = audit.list_entries()
    assert len(entries) == 1
    assert entries[0].entity == "intervention"
    assert entries[0].after == {"statut": "Terminée"}


# ---------------------------------------------------------------------- #
# Documents attachés
# ---------------------------------------------------------------------- #
def test_documents_attach_list_delete(tmp_path: Path, db: Database) -> None:
    from app.documents import DocumentService

    svc = DocumentService(db)
    source = tmp_path / "rapport.pdf"
    source.write_bytes(b"%PDF-1.4 fake content")

    doc = svc.attach(
        entity="rapports", entity_id="42", source=source,
        uploaded_by="Bovo", notes="Test",
    )
    assert doc.id > 0
    assert doc.filename == "rapport.pdf"
    assert Path(doc.storage_path).exists()

    listed = svc.list_for("rapports", "42")
    assert len(listed) == 1
    assert listed[0].size_bytes > 0

    assert svc.delete(doc.id) is True
    assert not Path(doc.storage_path).exists()
    assert svc.list_for("rapports", "42") == []


# ---------------------------------------------------------------------- #
# « Se souvenir de moi » + auto-login
# ---------------------------------------------------------------------- #
def test_auth_auto_login_from_remembered_hash(db: Database) -> None:
    """L'auto-login local (mode legacy) est supprimé — le refresh token JWT
    du backend REST est désormais utilisé à la place (voir Session côté
    client). Ce test valide simplement que ``Settings.remember/forget``
    n'ouvre plus aucune régression côté SQLite."""
    from app.settings import Settings

    settings = Settings(db)
    settings.remember("Bovo", "fake-refresh-token-xyz")
    assert settings.remembered_username == "Bovo"
    assert settings.remembered_refresh_token == "fake-refresh-token-xyz"
    # Le hash legacy est purgé automatiquement.
    assert settings.remembered_hash == ""
    settings.forget()
    assert settings.remembered_username == ""
    assert settings.remembered_refresh_token == ""


def test_settings_forget_clears_remembered(db: Database) -> None:
    from app.settings import Settings

    settings = Settings(db)
    settings.remember("Bovo", "refresh_token_xyz")
    assert settings.remembered_username == "Bovo"
    assert settings.remembered_refresh_token == "refresh_token_xyz"
    settings.forget()
    assert settings.remembered_username == ""
    assert settings.remembered_refresh_token == ""


# ---------------------------------------------------------------------- #
# Export PDF : largeurs de colonnes calculées
# ---------------------------------------------------------------------- #
def test_compute_column_widths_respects_content(tmp_path: Path) -> None:
    from app.exporter import _compute_column_widths

    headers = ["ID", "Descripton très longue de la colonne", "Statut"]
    rows = [
        ["1", "Rapport d'inspection ITV du secteur Garonne A62", "Terminée"],
        ["2", "Autre", "En cours"],
    ]
    widths = _compute_column_widths(headers, rows, usable_w=1000.0)
    assert len(widths) == 3
    # La colonne « descripton longue » doit être plus large que « ID ».
    assert widths[1] > widths[0]
    assert widths[1] > widths[2]
    # La somme est conservée (usable_w).
    assert abs(sum(widths) - 1000.0) < 0.5
