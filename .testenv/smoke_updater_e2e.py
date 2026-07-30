"""Smoke test auto-update HTTP + SHA256 + silent install (mock msiexec).

Scénario end-to-end :
  1. Un serveur HTTP local sert un faux "MSI" (bytes arbitraires) + latest.json
  2. Le client (updater.check_for_update) détecte version 99.0.0 > courante
  3. install_update() télécharge le MSI, vérifie SHA256, lance msiexec
     (mocké pour ne rien lancer réellement)
"""
from __future__ import annotations
import hashlib
import http.server
import json
import socketserver
import sys
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "/app/bovo")

from app.updater import (
    UpdateInfo,
    check_for_update,
    install_update,
    _sha256_file,
    _download_msi,
)
from app.version import __version__

FAKE_MSI_PAYLOAD = b"MSI FAKE PAYLOAD " * 1024  # ~17 Ko
FAKE_MSI_SHA = hashlib.sha256(FAKE_MSI_PAYLOAD).hexdigest().lower()

# --- Serveur HTTP local mini ---
TMP = Path(tempfile.mkdtemp(prefix="bovo_updater_"))
(TMP / "Bovo-Setup.msi").write_bytes(FAKE_MSI_PAYLOAD)

latest_json = {
    "version": "99.0.0",
    "msi_url": "http://127.0.0.1:0/Bovo-Setup.msi",  # port rempli plus bas
    "sha256": FAKE_MSI_SHA,
    "size": len(FAKE_MSI_PAYLOAD),
    "release_notes": "Test HTTP + SHA256",
    "mandatory": False,
    "published_at": "2026-07-30T10:00:00+00:00",
}

class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(TMP), **kw)
    def log_message(self, *a):  # silence
        pass

with socketserver.TCPServer(("127.0.0.1", 0), Handler) as httpd:
    port = httpd.server_address[1]
    latest_json["msi_url"] = f"http://127.0.0.1:{port}/Bovo-Setup.msi"
    (TMP / "latest.json").write_text(json.dumps(latest_json), encoding="utf-8")

    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    print(f"HTTP server on :{port}, dir={TMP}")

    try:
        # 1. check_for_update via HTTP
        info = check_for_update(f"http://127.0.0.1:{port}/latest.json")
        assert info is not None, "check_for_update devrait détecter 99.0.0"
        assert info.latest_version == "99.0.0"
        assert info.sha256 == FAKE_MSI_SHA
        assert info.msi_url.startswith(f"http://127.0.0.1:{port}")
        print(f"[1/3] check_for_update OK — v{info.latest_version} sha={info.sha256[:12]}...")

        # 2. download + SHA256 check
        dest = TMP / "downloaded.msi"
        ok = _download_msi(info.msi_url, dest, expected_sha256=info.sha256)
        assert ok is True
        assert dest.exists()
        actual = _sha256_file(dest)
        assert actual == FAKE_MSI_SHA
        print(f"[2/3] _download_msi OK — {dest.stat().st_size} bytes, SHA256 vérifié")

        # 3. install_update : mock subprocess.Popen pour ne pas lancer msiexec
        launched = {"cmd": None, "flags": None}
        class _FakeProc:
            pass
        def _fake_popen(cmd, creationflags=0, **kw):
            launched["cmd"] = cmd
            launched["flags"] = creationflags
            return _FakeProc()
        with patch("app.updater.subprocess.Popen", side_effect=_fake_popen):
            ok = install_update(info, silent=True)
        assert ok is True, "install_update devrait lancer msiexec"
        cmd = launched["cmd"]
        assert cmd[0] == "msiexec"
        assert "/i" in cmd
        assert "/qn" in cmd
        assert "/norestart" in cmd
        assert any(str(TMP) in c or "downloaded.msi" in c or "Bovo-" in c for c in cmd), cmd
        print(f"[3/3] install_update OK — msiexec {' '.join(cmd[:4])}...")

        print("\n*** AUTO-UPDATE E2E OK ***")
    finally:
        httpd.shutdown()
