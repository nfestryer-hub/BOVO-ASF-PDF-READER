"""Tests V1.3 :

* Détection Jour/Nuit à partir du champ ``commentaire`` (renseigné par le
  parser Planning 2026) ou du champ ``objet``.
* Le RemotePlanner transmet les paramètres ``sort_by`` / ``sort_dir``
  au backend REST.
* L'API client injecte ces paramètres dans la query string.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_is_nuit_detects_commentaire() -> None:
    from app.models import Intervention, is_nuit

    iv = Intervention(
        ouvrage="X", objet="Curage",
        commentaire="Nuit: Oui — équipe 3",
    )
    assert is_nuit(iv) is True


def test_is_nuit_detects_objet_marker() -> None:
    from app.models import Intervention, is_nuit

    iv = Intervention(ouvrage="X", objet="Curage complet (Nuit)")
    assert is_nuit(iv) is True


def test_is_nuit_default_false() -> None:
    from app.models import Intervention, is_nuit

    iv = Intervention(ouvrage="X", objet="Curage complet")
    assert is_nuit(iv) is False


def test_api_client_passes_sort_params() -> None:
    """``list_interventions`` doit propager ``sort_by`` et ``sort_dir``."""
    from app.api_client import ApiClient

    calls: list[dict] = []

    class _FakeClient(ApiClient):
        def __init__(self) -> None:  # noqa: D401 - test stub
            pass

        def _request(self, method: str, path: str, **kw):
            calls.append({"method": method, "path": path, **kw})
            return []

    client = _FakeClient()
    client.list_interventions(sort_by="secteur", sort_dir="asc")
    assert calls, "aucun appel enregistré"
    params = calls[0]["params"]
    assert params["sort_by"] == "secteur"
    assert params["sort_dir"] == "asc"


def test_remote_planner_forwards_sort_to_fetch() -> None:
    """RemotePlanner.search doit pousser sort_by/sort_dir dans fetch_all."""
    from app.remote_services import RemotePlanner

    seen: list[dict] = []

    class _FakeClient:
        def fetch_all_interventions(self, **kwargs):
            seen.append(kwargs)
            return []

    planner = RemotePlanner(_FakeClient())
    planner.search(sort_by="date", sort_dir="asc")
    assert seen == [{"sort_by": "date", "sort_dir": "asc"}]


def test_remote_planner_no_sort_when_empty() -> None:
    """Si sort_by/sort_dir sont vides, ils ne sont pas envoyés au backend."""
    from app.remote_services import RemotePlanner

    seen: list[dict] = []

    class _FakeClient:
        def fetch_all_interventions(self, **kwargs):
            seen.append(kwargs)
            return []

    planner = RemotePlanner(_FakeClient())
    planner.search()
    assert seen == [{}]
