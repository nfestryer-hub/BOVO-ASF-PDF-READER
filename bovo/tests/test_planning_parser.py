"""Tests V1.2 — nouveau parser Planning ASF 2026 + pagination client.

Le format « Planning 2026.pdf » est un tableau en blocs autoroute
(``A63``, ``A64``, ``A641``…) suivis de lignes ouvrages. Le parser
doit détecter automatiquement ce format et extraire chaque intervention.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.api_client import ApiClient  # noqa: E402
from app.parser_pdf import PdfParser  # noqa: E402
from app.planning_pdf_parser import (  # noqa: E402
    is_planning_format, parse_planning_pdf,
)


PLANNING_PDF = Path("/tmp/planning2026.pdf")


def test_is_planning_format_detects_new_asf_pdf() -> None:
    """Le PDF Planning 2026 doit être détecté par l'heuristique."""
    if not PLANNING_PDF.exists():
        return  # skip si absent en CI
    assert is_planning_format(PLANNING_PDF) is True


def test_is_planning_format_rejects_old_bovo_listing() -> None:
    """Le listing historique ne doit PAS être classé Planning ASF."""
    old = ROOT / "sample" / "Listing_Ouvrages_BOVO.pdf"
    if not old.exists():
        return
    assert is_planning_format(old) is False


def test_parse_planning_pdf_extracts_interventions() -> None:
    """Le parser doit extraire les interventions du Planning ASF."""
    if not PLANNING_PDF.exists():
        return
    interventions = parse_planning_pdf(PLANNING_PDF)
    assert len(interventions) >= 5, f"Trop peu d'interventions: {len(interventions)}"
    # Chaque intervention doit avoir un ouvrage + une autoroute + des dates.
    for iv in interventions:
        assert iv.ouvrage, f"Intervention sans ouvrage : {iv}"
        assert iv.autoroute.startswith("A"), f"Autoroute invalide : {iv.autoroute}"
        assert iv.dates, f"Aucune date pour {iv.ouvrage}"
        for d in iv.dates:
            assert isinstance(d, date)


def test_parse_planning_marks_nuit_in_observations() -> None:
    """Les interventions marquées Oui en colonne Nuit doivent avoir
    ``Nuit: Oui`` dans les observations (pour la fiche planning)."""
    if not PLANNING_PDF.exists():
        return
    interventions = parse_planning_pdf(PLANNING_PDF)
    # Au moins une intervention doit être marquée Nuit (Oui).
    nuit_count = sum(1 for iv in interventions if "Nuit: Oui" in iv.observations)
    assert nuit_count >= 1, "Aucune intervention de nuit détectée."


def test_pdf_parser_auto_dispatches_to_planning_parser() -> None:
    """``PdfParser.parse_file`` doit auto-router vers le bon parser."""
    if not PLANNING_PDF.exists():
        return
    parser = PdfParser()
    interventions = parser.parse_file(PLANNING_PDF)
    # Si le fallback tabulaire avait été utilisé, on aurait 0 ou peu de
    # résultats (la structure du PDF n'est pas tabulaire).
    assert len(interventions) >= 5


def test_api_client_pagination_transparent() -> None:
    """``fetch_all_interventions`` doit paginer et agréger sans doublons."""
    client = ApiClient.__new__(ApiClient)
    client._client = MagicMock()
    # Simule 2 pages : 500 + 47.
    page1 = [{"id": i, "ouvrage": f"O{i}"} for i in range(500)]
    page2 = [{"id": i, "ouvrage": f"O{i}"} for i in range(500, 547)]
    client.list_interventions = MagicMock(side_effect=[page1, page2])

    rows = client.fetch_all_interventions()

    assert len(rows) == 547
    assert client.list_interventions.call_count == 2
    # 1er appel avec offset=0, 2ème avec offset=500.
    call_kwargs = [c.kwargs for c in client.list_interventions.call_args_list]
    assert call_kwargs[0]["offset"] == 0
    assert call_kwargs[1]["offset"] == 500


def test_api_client_pagination_single_page_stops_early() -> None:
    """Si la 1ère page est incomplète, on ne rappelle pas l'API."""
    client = ApiClient.__new__(ApiClient)
    client._client = MagicMock()
    client.list_interventions = MagicMock(return_value=[{"id": 1}] * 42)

    rows = client.fetch_all_interventions(page_size=500)

    assert len(rows) == 42
    assert client.list_interventions.call_count == 1
