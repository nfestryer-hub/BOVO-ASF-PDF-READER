"""Tests des correctifs V4 :

* PDF import : l'import doit maintenant fonctionner (bug ``pdf_parser`` corrigé).
* Persistance JSON : les clés critiques (URL serveur, refresh token) doivent
  survivre à un effacement de la base SQLite grâce au fichier JSON utilisateur.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import local_config  # noqa: E402
from app.api_client import ApiClient  # noqa: E402
from app.database import Database  # noqa: E402
from app.remote_services import RemotePlanner  # noqa: E402
from app.settings import Settings  # noqa: E402


SAMPLE_PDF = ROOT / "sample" / "Listing_Ouvrages_BOVO.pdf"


# --------------------------------------------------------------------- #
# 1. Bug fixé : import PDF (mauvais nom de module -> parser_pdf).
# --------------------------------------------------------------------- #
def test_remote_planner_import_pdfs_no_import_error(tmp_path: Path) -> None:
    """``RemotePlanner.import_pdfs`` ne doit PLUS échouer à cause d'un
    module ``pdf_parser`` inexistant. Le module correct est ``parser_pdf``.
    """
    if not SAMPLE_PDF.exists():
        pytest.skip("PDF d'exemple absent")

    client = MagicMock(spec=ApiClient)
    client.list_interventions.return_value = []
    client.create_intervention.side_effect = lambda payload: {**payload, "id": 1}

    planner = RemotePlanner(client)
    result = planner.import_pdfs([SAMPLE_PDF])

    # Aucune erreur ne doit être remontée (le bug provoquait une ImportError).
    assert result.errors == [], f"Erreurs inattendues : {result.errors}"
    assert result.files_processed == 1
    # Le PDF d'exemple contient 30+ interventions.
    assert result.interventions_created > 10


# --------------------------------------------------------------------- #
# 2. Persistance JSON : le fichier local_config sauvegarde côté user.
# --------------------------------------------------------------------- #
def test_local_config_roundtrip(tmp_path: Path, monkeypatch) -> None:
    """local_config.set_value / get retournent la valeur écrite."""
    monkeypatch.setattr(local_config, "_user_config_dir", lambda: tmp_path)
    local_config.set_value("server_url", "http://192.168.1.42:8000")
    assert local_config.get("server_url") == "http://192.168.1.42:8000"
    assert (tmp_path / "bovo_config.json").exists()


def test_settings_mirrors_server_url_to_json(tmp_path: Path, monkeypatch) -> None:
    """L'écriture du server_url dans Settings doit mettre à jour le JSON."""
    monkeypatch.setattr(local_config, "_user_config_dir", lambda: tmp_path)
    db_path = tmp_path / "settings.db"
    db = Database(db_path)
    settings = Settings(db)
    settings.server_url = "http://bovo.local:8000"
    db.close()

    # Le fichier JSON contient l'URL, même si on efface la DB.
    assert local_config.get("server_url") == "http://bovo.local:8000"


def test_settings_restores_server_url_from_json_after_db_wipe(
    tmp_path: Path, monkeypatch,
) -> None:
    """Si la base SQLite est effacée, Settings récupère l'URL depuis le JSON."""
    monkeypatch.setattr(local_config, "_user_config_dir", lambda: tmp_path)
    db_path = tmp_path / "settings.db"

    # 1er lancement : on configure l'URL.
    db1 = Database(db_path)
    settings1 = Settings(db1)
    settings1.server_url = "http://server.bovo:8000"
    settings1.remember("Bovo", "REFRESH_TOKEN_ABC")
    db1.close()

    # Simulation de la perte de la DB (poste réinitialisé / réinstallation).
    db_path.unlink()

    # 2ème lancement : la DB est reconstruite vide, mais l'URL + le token
    # doivent être restaurés depuis le fichier JSON utilisateur.
    db2 = Database(db_path)
    settings2 = Settings(db2)
    assert settings2.server_url == "http://server.bovo:8000"
    assert settings2.remembered_username == "Bovo"
    assert settings2.remembered_refresh_token == "REFRESH_TOKEN_ABC"
    db2.close()


def test_settings_forget_wipes_both_stores(tmp_path: Path, monkeypatch) -> None:
    """``settings.forget()`` doit vider le JSON ET la DB."""
    monkeypatch.setattr(local_config, "_user_config_dir", lambda: tmp_path)
    db = Database(tmp_path / "settings.db")
    settings = Settings(db)
    settings.remember("Bovo", "TOKEN_XYZ")
    assert local_config.get("remembered_refresh_token") == "TOKEN_XYZ"

    settings.forget()
    assert settings.remembered_refresh_token == ""
    assert local_config.get("remembered_refresh_token") == ""
    db.close()
