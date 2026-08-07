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
    """Version publiée plus récente → UpdateInfo peuplé (msi_url + sha256)."""
    latest = tmp_path / "latest.json"
    latest.write_text(
        json.dumps({
            "version": "99.0.0",
            "msi_url": "http://serveur/updates/Bovo-Setup.msi",
            "msi_path": "\\\\SERVEUR\\Partage\\Bovo\\Bovo-Setup.msi",
            "sha256": "abcdef" + "0" * 58,
            "size": 60_000_000,
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
    assert info.msi_url.startswith("http://")
    assert info.msi_path.endswith("Bovo-Setup.msi")
    assert info.sha256 == "abcdef" + "0" * 58
    assert info.size == 60_000_000


def test_check_payload_incomplet(tmp_path: Path) -> None:
    """Payload sans msi_url NI msi_path → None (pas d'installation possible)."""
    latest = tmp_path / "latest.json"
    latest.write_text(json.dumps({"version": "99.0.0"}), encoding="utf-8")
    assert check_for_update(latest) is None


def test_check_payload_msi_url_only(tmp_path: Path) -> None:
    """Payload avec msi_url seul → OK (canal HTTP)."""
    latest = tmp_path / "latest.json"
    latest.write_text(
        json.dumps({
            "version": "99.0.0",
            "msi_url": "http://serveur/x.msi",
        }),
        encoding="utf-8",
    )
    info = check_for_update(latest)
    assert info is not None
    assert info.msi_url == "http://serveur/x.msi"
    assert info.msi_path == ""


def test_check_payload_msi_path_only(tmp_path: Path) -> None:
    """Payload avec msi_path seul → OK (canal UNC)."""
    latest = tmp_path / "latest.json"
    latest.write_text(
        json.dumps({
            "version": "99.0.0",
            "msi_path": "\\\\SERVEUR\\Partage\\x.msi",
        }),
        encoding="utf-8",
    )
    info = check_for_update(latest)
    assert info is not None
    assert info.msi_url == ""
    assert info.msi_path.endswith("x.msi")


def test_check_json_invalide(tmp_path: Path) -> None:
    """JSON malformé → None (log WARNING, jamais d'exception propagée)."""
    latest = tmp_path / "latest.json"
    latest.write_text("{ not json", encoding="utf-8")
    assert check_for_update(latest) is None


def test_sha256_file(tmp_path: Path) -> None:
    """_sha256_file calcule le SHA256 en streaming (économe RAM)."""
    from app.updater import _sha256_file

    payload = b"hello world"
    p = tmp_path / "sample.bin"
    p.write_bytes(payload)
    # sha256(b"hello world") = b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9
    assert _sha256_file(p) == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_download_msi_sha256_mismatch(tmp_path: Path, monkeypatch) -> None:
    """Si le SHA256 attendu ne matche pas, le .part est purgé et False."""
    from app.updater import _download_msi

    fake_msi = b"MSI PAYLOAD FAKE"

    class _FakeResp:
        headers = {"Content-Length": str(len(fake_msi))}

        def raise_for_status(self) -> None:  # noqa: D401
            pass

        def iter_content(self, chunk_size: int):  # noqa: D401
            yield fake_msi

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    def _fake_get(*_args, **_kwargs):
        return _FakeResp()

    import requests as req_mod
    monkeypatch.setattr(req_mod, "get", _fake_get)

    dest = tmp_path / "target.msi"
    ok = _download_msi(
        "http://fake/msi", dest, expected_sha256="deadbeef" * 8,
    )
    assert ok is False, "SHA256 mismatch devrait retourner False"
    assert not dest.exists(), "Le fichier partiel doit être purgé"


def test_download_msi_sha256_ok(tmp_path: Path, monkeypatch) -> None:
    """SHA256 correct → fichier persisté et True."""
    from app.updater import _download_msi, _sha256_file

    fake_msi = b"MSI PAYLOAD OK"

    class _FakeResp:
        headers = {"Content-Length": str(len(fake_msi))}
        def raise_for_status(self) -> None: pass
        def iter_content(self, chunk_size: int):
            yield fake_msi
        def __enter__(self): return self
        def __exit__(self, *_a): return False

    import requests as req_mod
    monkeypatch.setattr(req_mod, "get", lambda *_a, **_k: _FakeResp())

    dest = tmp_path / "target.msi"
    # On calcule le SHA256 attendu localement (round-trip)
    ref = tmp_path / "ref.bin"
    ref.write_bytes(fake_msi)
    expected = _sha256_file(ref)

    ok = _download_msi("http://fake/msi", dest, expected_sha256=expected)
    assert ok is True
    assert dest.exists()
    assert _sha256_file(dest) == expected
