"""Tests de l'auto-updater (comparaison versions + lecture latest.json)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.updater import (  # noqa: E402
    UpdateInfo,
    _parse_version,
    check_for_update,
)


def test_parse_version_simple() -> None:
    assert _parse_version("1.2.3") == (1, 2, 3)


def test_parse_version_4_parts() -> None:
    assert _parse_version("1.2.3.4") == (1, 2, 3, 4)


def test_parse_version_prerelease() -> None:
    # Les suffixes de pré-release sont ignorés.
    assert _parse_version("1.2.3-beta1") == (1, 2, 3)


def test_parse_version_short() -> None:
    assert _parse_version("1.2") == (1, 2)


def test_parse_version_tolere_non_num() -> None:
    assert _parse_version("v.beta") == (0, 0)


def test_check_no_source_returns_none() -> None:
    assert check_for_update("") is None


def test_check_source_absent_returns_none(tmp_path: Path) -> None:
    # Chemin inexistant : pas d'erreur, retourne None.
    assert check_for_update(tmp_path / "nope.json") is None


def test_check_older_returns_none(tmp_path: Path) -> None:
    """Version publiée plus ancienne → None (pas de MAJ à proposer)."""
    from app.version import __version__ as current

    latest = tmp_path / "latest.json"
    latest.write_text(
        json.dumps({"version": "0.0.1", "msi_path": "\\\\dummy\\Bovo.msi"}),
        encoding="utf-8",
    )
    # __version__ doit être > 0.0.1
    assert _parse_version(current) > _parse_version("0.0.1")
    assert check_for_update(latest) is None


def test_check_newer_returns_updateinfo(tmp_path: Path) -> None:
    """Version publiée plus récente → UpdateInfo peuplé."""
    latest = tmp_path / "latest.json"
    latest.write_text(
        json.dumps({
            "version": "99.0.0",
            "msi_path": "\\\\SERVEUR\\Partage\\Bovo\\Bovo-Setup.msi",
            "release_notes": "Fix truc",
            "mandatory": True,
        }),
        encoding="utf-8",
    )
    info = check_for_update(latest)
    assert info is not None
    assert isinstance(info, UpdateInfo)
    assert info.latest_version == "99.0.0"
    assert info.mandatory is True
    assert "Fix truc" in info.release_notes
    assert info.msi_path.endswith("Bovo-Setup.msi")


def test_check_payload_incomplet(tmp_path: Path) -> None:
    """Payload sans msi_path → None (pas de plantage)."""
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps({"version": "99.0.0"}), encoding="utf-8")
    assert check_for_update(latest) is None


def test_check_json_invalide(tmp_path: Path) -> None:
    """JSON malformé → None (log WARNING, jamais d'exception propagée)."""
    latest = tmp_path / "latest.json"
    latest.write_text("{ not json", encoding="utf-8")
    assert check_for_update(latest) is None
