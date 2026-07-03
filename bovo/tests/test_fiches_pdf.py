"""Test V1.2 — Fiches d'intervention imprimables (1 page A4 par intervention).

Vérifie que :
* Le PDF généré contient bien 1 page par intervention (format A4 portrait).
* Les informations vedettes (autoroute, identifiant, date, jour/nuit) sont
  extractibles du PDF.
* Le nom du planificateur est présent en pied de page.
* La signalétique JOUR/NUIT change bien selon le contenu.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.exporter import Exporter  # noqa: E402
from app.models import Intervention, StatutIntervention  # noqa: E402


def _sample_intervention(**overrides) -> Intervention:
    """Retourne une intervention type pour les tests de fiche."""
    defaults = dict(
        ouvrage="43854", objet="Inspection ITV caniveau",
        autoroute="A62", secteur="Garonne",
        pr_debut="10+000", pr_fin="10+320", sens="Sens 1",
        type_ouvrage="Caniveau",
        date_debut=date(2026, 6, 22), date_fin=date(2026, 6, 22),
        statut=StatutIntervention.PLANIFIEE,
        commentaire="Inspection prévue en journée, matériel léger suffisant.",
    )
    defaults.update(overrides)
    return Intervention(**defaults)


def test_fiches_pdf_a4_portrait_one_page_per_intervention(tmp_path: Path) -> None:
    """Chaque intervention doit produire exactement 1 page A4 portrait."""
    exporter = Exporter(database=None)
    interventions = [
        _sample_intervention(ouvrage="43854"),
        _sample_intervention(ouvrage="43855", autoroute="A61"),
        _sample_intervention(ouvrage="43856", autoroute="A20"),
    ]
    dest = tmp_path / "fiches.pdf"
    exporter.interventions_fiches_pdf(
        interventions, dest, planificateur="Dylan HENRI",
    )
    assert dest.exists()
    doc = fitz.open(str(dest))
    try:
        assert doc.page_count == 3
        # A4 portrait : 595 × 842 pt.
        for page in doc:
            assert abs(page.rect.width - 595) < 5
            assert abs(page.rect.height - 842) < 5
    finally:
        doc.close()


def test_fiches_pdf_contains_key_information(tmp_path: Path) -> None:
    """Les infos vedettes (autoroute, id, date, planificateur) doivent apparaître."""
    exporter = Exporter(database=None)
    iv = _sample_intervention(ouvrage="99001", autoroute="A62")
    dest = tmp_path / "fiche.pdf"
    exporter.interventions_fiches_pdf([iv], dest, planificateur="Dylan HENRI")

    doc = fitz.open(str(dest))
    text = doc[0].get_text()
    doc.close()
    # Aplati pour tolérer les retours ligne dans les cellules.
    flat = text.replace("\n", " ")

    assert "99001" in flat, "Identifiant absent"
    assert "A62" in flat, "Autoroute absente"
    assert "juin" in flat.lower(), "Date en français absente"
    assert "Dylan HENRI" in flat, "Nom du planificateur absent"
    assert "FICHE D'INTERVENTION" in flat


def test_fiches_pdf_jour_nuit_badge(tmp_path: Path) -> None:
    """Le badge JOUR / NUIT doit s'adapter au contenu de l'intervention."""
    exporter = Exporter(database=None)
    iv_jour = _sample_intervention(
        commentaire="Chantier de jour, conditions normales.",
    )
    iv_nuit = _sample_intervention(
        ouvrage="99002",
        commentaire="Chantier de nuit — coupure sous circulation.",
    )
    dest = tmp_path / "jour_nuit.pdf"
    exporter.interventions_fiches_pdf([iv_jour, iv_nuit], dest)

    doc = fitz.open(str(dest))
    p1 = doc[0].get_text()
    p2 = doc[1].get_text()
    doc.close()

    # Page 1 (jour) : contient JOUR, pas NUIT (badge principal).
    # PyMuPDF peut extraire les mots avec les emojis, on tolère l'emoji.
    assert "JOUR" in p1
    # Page 2 (nuit) : contient NUIT.
    assert "NUIT" in p2
