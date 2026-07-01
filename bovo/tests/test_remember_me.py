"""Tests de la fonctionnalité 'Se souvenir de moi' (auto-login via JWT).

Vérifie :

* la persistance du refresh_token dans SQLite via ``Settings.remember`` ;
* la restauration du token après un cycle close/reopen (checkpoint WAL) ;
* la distinction entre erreur réseau (token conservé) et erreur token
  invalide (token à purger côté appelant).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.api_client import ApiClient, ApiError  # noqa: E402
from app.database import Database  # noqa: E402
from app.remote_services import (  # noqa: E402
    AutoLoginNetworkError,
    RemoteAuthService,
)
from app.session import Session  # noqa: E402
from app.settings import Settings  # noqa: E402


# --------------------------------------------------------------------- #
# Persistance : le refresh_token survit à un close/reopen de la DB.
# --------------------------------------------------------------------- #
def test_remember_persists_across_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "settings.db"

    # 1er lancement : on écrit
    db1 = Database(db_path)
    settings1 = Settings(db1)
    settings1.remember("Bovo", "REFRESH_TOKEN_ABC_" + "x" * 100)
    saved = settings1.remembered_refresh_token
    assert saved.startswith("REFRESH_TOKEN_ABC_")
    db1.close()

    # 2ème lancement : on relit — DOIT retourner le même token
    db2 = Database(db_path)
    settings2 = Settings(db2)
    assert settings2.remembered_username == "Bovo"
    assert settings2.remembered_refresh_token == saved
    db2.close()


def test_forget_clears_everything(tmp_path: Path) -> None:
    db_path = tmp_path / "s.db"
    db = Database(db_path)
    settings = Settings(db)
    settings.remember("Alice", "tok_" + "y" * 50)
    settings.forget()
    assert settings.remembered_username == ""
    assert settings.remembered_refresh_token == ""
    db.close()


# --------------------------------------------------------------------- #
# try_auto_login : succès, token expiré, réseau down
# --------------------------------------------------------------------- #
def _make_client(tmp_path: Path) -> ApiClient:
    """Client isolé (ne fera aucun appel réel dans ces tests)."""
    return ApiClient(base_url="http://127.0.0.1:65533")


def test_try_auto_login_returns_none_when_token_empty(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    session = Session(client=client)
    auth = RemoteAuthService(client, session)
    assert auth.try_auto_login("") is None


def test_try_auto_login_purges_on_401(tmp_path: Path, monkeypatch) -> None:
    """Token expiré/révoqué (HTTP 401) → retourne None, PAS d'exception."""
    client = _make_client(tmp_path)
    session = Session(client=client)
    auth = RemoteAuthService(client, session)

    def _fake_refresh() -> None:
        raise ApiError(401, "Token expired")

    monkeypatch.setattr(client, "refresh_access_token", _fake_refresh)
    result = auth.try_auto_login("expired_token")
    assert result is None
    # Le client doit être vidé (JWT stateless)
    assert client.tokens.refresh_token == ""


def test_try_auto_login_raises_network_error(tmp_path: Path, monkeypatch) -> None:
    """Serveur injoignable → AutoLoginNetworkError (token conservable)."""
    client = _make_client(tmp_path)
    session = Session(client=client)
    auth = RemoteAuthService(client, session)

    from requests.exceptions import ConnectionError as ReqConnErr

    def _boom() -> None:
        raise ReqConnErr("Connection refused")

    monkeypatch.setattr(client, "refresh_access_token", _boom)
    with pytest.raises(AutoLoginNetworkError):
        auth.try_auto_login("some_valid_looking_token")


def test_try_auto_login_success(tmp_path: Path, monkeypatch) -> None:
    """Succès : refresh OK, me() OK → RemoteUser rebindé sur la session."""
    client = _make_client(tmp_path)
    session = Session(client=client)
    auth = RemoteAuthService(client, session)

    monkeypatch.setattr(client, "refresh_access_token", lambda: None)
    monkeypatch.setattr(
        client, "me",
        lambda: {"id": 42, "username": "Bovo", "role": "Admin", "full_name": "X"},
    )
    user = auth.try_auto_login("valid_token")
    assert user is not None
    assert user.username == "Bovo"
    assert user.role == "Admin"
    assert session.user is not None
    assert session.user.id == 42
