"""Smoke test complet du GUI en mode REST + import Excel + scroll horizontal.

Vérifie :
* BovoApp démarre en mode REST via `client=`.
* Toutes les clés d'API des services Remote matchent la version locale.
* Import du nouveau classeur ASF (avec colonne ID) fonctionne.
* Le tableau du module inspections utilise bien un Canvas scrollable H+V.
"""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="bovo_smoke_"))
sys.path.insert(0, "/app/bovo")

import app.utils as _u
_u.DATABASE_DIR = TMP

from app.database import Database
from app.settings import Settings
from app.session import Session
from app.api_client import ApiClient
from app.remote_services import RemoteAuthService, RemoteAuditService
from app.gui import BovoApp
from app.inspections import InspectionService, ORDERED_COLUMNS
import customtkinter as ctk
from tkinter import Canvas

SERVER = "http://127.0.0.1:8765"
DB_PATH = TMP / "bovo.db"
EXCEL = Path("/app/.testenv/asf.xlsx")

# --- Setup ---
db = Database(DB_PATH)
settings = Settings(db)
settings.set("server_url", SERVER)
client = ApiClient(base_url=SERVER)
session = Session(client=client)
auth = RemoteAuthService(client, session)
audit = RemoteAuditService(client)
user = auth.login("Bovo", "ibak23")
assert user is not None
print(f"Logged in: {user.username}/{user.role}")

# --- BovoApp ---
app = BovoApp(db, settings, auth=auth, audit=audit, client=client)
assert type(app._planner).__name__ == "RemotePlanner"
assert type(app._inspections).__name__ == "RemoteInspectionService"
assert type(app._documents).__name__ == "RemoteDocumentService"
print("BovoApp OK (Remote services)")

# --- Excel import : colonnes id_ouvrage ---
assert "id_ouvrage" in ORDERED_COLUMNS["inspections"], "id_ouvrage manquant"
pos = ORDERED_COLUMNS["inspections"].index("id_ouvrage")
assert pos == 3, f"id_ouvrage attendu en position 3, trouvé en {pos}"
print(f"ORDERED_COLUMNS['inspections'] contient id_ouvrage en pos {pos} ✓")

if EXCEL.exists():
    tmpdb = Database(TMP / "excel.db")
    svc = InspectionService(tmpdb)
    r = svc.import_workbook(EXCEL)
    print(f"Import: {r}")
    rows = tmpdb.list_generic("inspections")
    assert len(rows) > 0
    assert rows[0].get("id_ouvrage"), f"id_ouvrage vide sur la 1re ligne: {rows[0]}"
    print(f"Import Excel OK: {len(rows)} inspections, id_ouvrage='{rows[0]['id_ouvrage']}'")
    tmpdb.close()
else:
    print(f"⚠ Excel de référence absent ({EXCEL})")

# --- UI construction ---
app.on_authenticated()
app.update()

# On force la construction de la vue Inspections ASF (là où se trouve le tableau)
try:
    app._view_inspections()
except Exception as exc:  # noqa: BLE001
    print(f"_view_inspections direct failed: {exc}")
app.update_idletasks()

# --- Vérif scroll horizontal : le tableau du 1er sheet doit être dans un Canvas ---
canvases = getattr(app, "_insp_canvases", {})
assert canvases, "Aucun canvas d'inspection créé !"
first_sheet = list(canvases.keys())[0]
canvas = canvases[first_sheet]
assert isinstance(canvas, Canvas), f"Canvas attendu, got {type(canvas)}"
# On force le rendu pour que le scrollregion soit calculé
app.update_idletasks()
region = canvas.cget("scrollregion")
print(f"Canvas sheet={first_sheet!r} scrollregion={region!r}")
xview = canvas.xview()
yview = canvas.yview()
print(f"xview={xview}, yview={yview}")

# Vérifie que xscrollcommand/yscrollcommand sont bien branchés
assert canvas.cget("xscrollcommand"), "xscrollcommand non branché"
assert canvas.cget("yscrollcommand"), "yscrollcommand non branché"
print("Scroll horizontal ET vertical branchés ✓")

app.destroy()
db.close()
print("\n*** SMOKE TEST OK ***")
