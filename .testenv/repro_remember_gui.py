"""Repro FULL du bug 'Se souvenir de moi' (non-régression).

Vérifie que le refresh_token survit à un cycle close/reopen SQLite (WAL
checkpoint) et que try_auto_login réussit ensuite.
"""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="bovo_repro_"))
sys.path.insert(0, "/app/bovo")
import app.utils as _u
_u.DATABASE_DIR = TMP

from app.database import Database
from app.settings import Settings
from app.session import Session
from app.api_client import ApiClient
from app.remote_services import RemoteAuthService
from app.gui import LoginDialog
import customtkinter as ctk

SERVER = "http://127.0.0.1:8765"
USER, PWD = "Bovo", "ibak23"
DB_PATH = TMP / "bovo.db"

# --- Phase 1 ---
db1 = Database(DB_PATH)
settings1 = Settings(db1)
settings1.set("server_url", SERVER)
client1 = ApiClient(base_url=settings1.server_url)
session1 = Session(client=client1)
auth1 = RemoteAuthService(client1, session1)
root = ctk.CTk()
root.withdraw()

def _end():
    root.after(50, root.quit)

dlg = LoginDialog(root, auth1, on_success=_end, on_cancel=_end, settings=settings1)
dlg.update()
dlg._username_var.set(USER)
dlg._password_var.set(PWD)
dlg._remember_me.set(True)
dlg._attempt_login()
root.update()
root.after(100, root.quit)
root.mainloop()

tok = settings1.remembered_refresh_token
print(f"Phase 1 - remembered_refresh_token: {'OK ('+str(len(tok))+' chars)' if tok else 'EMPTY'}")
db1.close()
root.destroy()

# --- Phase 2 ---
db2 = Database(DB_PATH)
settings2 = Settings(db2)
tok2 = settings2.remembered_refresh_token
assert tok2, "BUG REPRODUIT : refresh_token perdu"
client2 = ApiClient(base_url=settings2.server_url)
session2 = Session(client=client2)
auth2 = RemoteAuthService(client2, session2)
user = auth2.try_auto_login(tok2)
assert user is not None, "auto-login échoue"
print(f"Phase 2 - AUTO-LOGIN OK ({user.username}/{user.role})")
db2.close()
print("\n*** REMEMBER-ME OK ***")
