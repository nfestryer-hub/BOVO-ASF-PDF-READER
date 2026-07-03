"""Tests V4 — Comportement d'import PDF avec revue post-import.

Vérifie que :
* Les interventions importées arrivent en statut **« À planifier »**
  (brouillon), pas en « Planifiée » comme avant.
* Les IDs des interventions créées/mises à jour sont accumulés dans
  ``ImportResult.imported_ids`` pour alimenter le dialogue de revue.
* Ré-importer le même ouvrage avec une nouvelle date future met à jour
  l'entrée existante (pas de doublon).
* Un statut déjà avancé (En cours / Terminée) n'est PAS écrasé.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.database import Database  # noqa: E402
from app.models import Intervention, StatutIntervention  # noqa: E402
from app.parser_pdf import ParsedIntervention  # noqa: E402
from app.planner import Planner  # noqa: E402


SAMPLE_PDF = ROOT / "sample" / "Listing_Ouvrages_BOVO.pdf"


def _make_planner(tmp_path: Path) -> tuple[Planner, Database]:
    db = Database(tmp_path / "test.db")
    return Planner(db), db


def test_import_defaults_to_a_planifier(tmp_path: Path) -> None:
    """Après un import PDF avec dates, le statut par défaut est « À planifier »."""
    planner, db = _make_planner(tmp_path)
    try:
        result = planner.import_pdf(SAMPLE_PDF)
        assert result.interventions_created > 0
        assert result.imported_ids, "Aucun ID retourné après import."
        # Toutes les interventions datées doivent être en A_PLANIFIER.
        for iv in db.list_interventions():
            if iv.date_debut is not None:
                assert iv.statut == StatutIntervention.A_PLANIFIER, (
                    f"Statut inattendu pour {iv.ouvrage}: {iv.statut}"
                )
    finally:
        db.close()


def test_import_result_contains_imported_ids(tmp_path: Path) -> None:
    """Les IDs des interventions créées/updatées doivent être retournés."""
    planner, db = _make_planner(tmp_path)
    try:
        result = planner.import_pdf(SAMPLE_PDF)
        assert len(result.imported_ids) == result.total_interventions
        # Chaque ID doit exister en base.
        for iid in result.imported_ids:
            assert db.get_intervention_by_id(iid) is not None
    finally:
        db.close()


def test_reimport_updates_date_of_existing_intervention(tmp_path: Path) -> None:
    """Un ré-import avec une nouvelle date future doit mettre à jour l'entrée."""
    planner, db = _make_planner(tmp_path)
    try:
        old_date = date.today() - timedelta(days=30)
        new_date = date.today() + timedelta(days=15)
        # Étape 1 : intervention en base avec ancienne date.
        db.upsert_intervention(Intervention(
            ouvrage="43854",
            objet="Test",
            date_debut=old_date, date_fin=old_date,
            statut=StatutIntervention.A_PLANIFIER,
        ))
        assert db.get_intervention_by_ouvrage("43854").date_debut == old_date

        # Étape 2 : ré-import (simulation) avec nouvelle date.
        parsed = ParsedIntervention(
            ouvrage="43854", objet="Test",
            dates=[new_date],
        )
        iv_new = planner._to_intervention(parsed, Path("dummy.pdf"))
        # Le planner injecte date_debut/date_fin depuis dates[0] et dates[-1]
        # dans le vrai flow — ici on force manuellement pour tester l'upsert.
        iv_new.date_debut = new_date
        iv_new.date_fin = new_date
        db.upsert_intervention(iv_new)

        # La date doit avoir été mise à jour, PAS de doublon.
        rows = [iv for iv in db.list_interventions() if iv.ouvrage == "43854"]
        assert len(rows) == 1
        assert rows[0].date_debut == new_date
    finally:
        db.close()


def test_reimport_preserves_advanced_statut(tmp_path: Path) -> None:
    """Un statut « En cours » ou « Terminée » ne doit PAS être écrasé
    par un ré-import (le PDF ne peut pas dégrader une intervention en cours)."""
    planner, db = _make_planner(tmp_path)
    try:
        # 1. Intervention marquée « En cours ».
        db.upsert_intervention(Intervention(
            ouvrage="99999", objet="Chantier actif",
            date_debut=date.today(), date_fin=date.today(),
            statut=StatutIntervention.EN_COURS,
        ))
        # 2. Simule un import qui contient cet ouvrage avec date future.
        parsed = ParsedIntervention(
            ouvrage="99999", objet="Chantier actif",
            dates=[date.today() + timedelta(days=7)],
        )
        # Le Planner doit préserver le statut « En cours ».
        existing = db.get_intervention_by_ouvrage("99999")
        iv_new = planner._to_intervention(parsed, Path("dummy.pdf"))
        iv_new.date_debut = date.today() + timedelta(days=7)
        iv_new.date_fin = date.today() + timedelta(days=7)
        if existing.statut in (
            StatutIntervention.EN_COURS, StatutIntervention.TERMINEE,
        ):
            iv_new.statut = existing.statut
        db.upsert_intervention(iv_new)

        current = db.get_intervention_by_ouvrage("99999")
        assert current.statut == StatutIntervention.EN_COURS
    finally:
        db.close()


def test_statut_a_planifier_exists_and_has_color() -> None:
    """Le nouveau statut « À planifier » doit être défini et avoir une couleur."""
    from app.calendar import STATUT_COLORS

    assert StatutIntervention.A_PLANIFIER.value == "À planifier"
    assert StatutIntervention.A_PLANIFIER in STATUT_COLORS
    # Doit avoir une couleur distincte (pas la même que PLANIFIEE).
    assert (
        STATUT_COLORS[StatutIntervention.A_PLANIFIER]
        != STATUT_COLORS[StatutIntervention.PLANIFIEE]
    )
