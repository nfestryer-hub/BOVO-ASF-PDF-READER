"""Smoke test : sélection multiple + suppression groupée des interventions
et des lignes de modules ASF.

Scénario :
  1. Login admin
  2. Crée 3 interventions via API
  3. Ouvre BovoApp, va sur Interventions
  4. Coche 2 lignes → bouton 'Supprimer sélection (2)' actif
  5. Simule le clic sur Delete → vérifie qu'il n'en reste qu'1
  6. Idem pour un module ASF (Inspections) : import + coche + suppression
"""
from __future__ import annotations
import os, sys, tempfile
from pathlib import Path
from unittest.mock import patch

TMP = Path(tempfile.mkdtemp(prefix="bovo_multiselect_"))
sys.path.insert(0, "/app/bovo")

import app.utils as _u
_u.DATABASE_DIR = TMP

from app.database import Database
from app.settings import Settings
from app.session import Session
from app.api_client import ApiClient
from app.remote_services import RemoteAuthService, RemoteAuditService
from app.gui import BovoApp
from app.inspections import ORDERED_COLUMNS
import customtkinter as ctk

SERVER = "http://127.0.0.1:8765"
DB_PATH = TMP / "bovo.db"

db = Database(DB_PATH)
settings = Settings(db)
settings.set("server_url", SERVER)
client = ApiClient(base_url=SERVER)
session = Session(client=client)
auth = RemoteAuthService(client, session)
audit = RemoteAuditService(client)
user = auth.login("Bovo", "ibak23")
assert user is not None
print(f"Logged in: {user.username}")

# Nettoie et crée 3 interventions
existing = client.list_interventions()
for iv in existing:
    try:
        client.delete_intervention(iv["id"])
    except Exception:
        pass

created = []
for i in range(3):
    iv = client.create_intervention({
        "ouvrage": f"OUV-MULTI-{i:03d}",
        "objet": f"Test multi-select #{i}",
        "autoroute": "A62",
        "secteur": "S1",
        "commentaire": "",
    })
    created.append(iv["id"])
print(f"Créées : {len(created)} interventions IDs={created}")

app = BovoApp(db, settings, auth=auth, audit=audit, client=client)
app.on_authenticated()
app._view_interventions()
app.update_idletasks()

# Vérif : bouton présent, désactivé au départ
assert app._iv_selected_btn is not None, "Bouton delete manquant"
state = app._iv_selected_btn.cget("state")
text = app._iv_selected_btn.cget("text")
print(f"Bouton initial : state={state}, text={text!r}")
assert state == "disabled"

# Coche 2 interventions
app._toggle_intervention(created[0], True)
app._toggle_intervention(created[1], True)
state = app._iv_selected_btn.cget("state")
text = app._iv_selected_btn.cget("text")
print(f"Après 2 coches : state={state}, text={text!r}")
assert state == "normal"
assert "(2)" in text

# Simule le clic Supprimer (mock du messagebox pour éviter interaction)
with patch("app.gui.messagebox.askyesno", return_value=True), \
     patch("app.gui.messagebox.showinfo"), \
     patch("app.gui.messagebox.showwarning"):
    app._delete_selected_interventions()

remaining = client.list_interventions()
remaining_ids = [iv["id"] for iv in remaining if iv["id"] in created]
print(f"Restant après suppression multi : {len(remaining_ids)} (attendu 1)")
assert len(remaining_ids) == 1
assert remaining_ids[0] == created[2]  # celui qu'on n'avait pas coché
print("Suppression multi INTERVENTIONS OK ✓")

# --- Test module ASF (inspections) ---
# Ajout de 3 lignes via API modules
sheet = "inspections"
mod_ids = []
for i in range(3):
    r = client._request("POST", f"/api/modules/{sheet}", json={
        "data": {"n_inspection": f"INSP-{i:03d}", "date": "2026-07-30", "id_ouvrage": f"OUV-{i}"},
    })
    mod_ids.append(r["id"])
print(f"\nCréées : 3 lignes {sheet} IDs={mod_ids}")

app._view_inspections()
app.update_idletasks()
btn = app._selected_module_btn[sheet]
assert btn is not None
assert btn.cget("state") == "disabled"

app._toggle_module_row(sheet, mod_ids[0], True)
app._toggle_module_row(sheet, mod_ids[1], True)
assert btn.cget("state") == "normal"
assert "(2)" in btn.cget("text")

with patch("app.gui.messagebox.askyesno", return_value=True), \
     patch("app.gui.messagebox.showinfo"), \
     patch("app.gui.messagebox.showwarning"):
    app._delete_selected_module_rows(sheet)

remaining_rows = client._request("GET", f"/api/modules/{sheet}")
remaining_mod_ids = [r["id"] for r in remaining_rows if r["id"] in mod_ids]
print(f"Restant après suppression multi module: {len(remaining_mod_ids)} (attendu 1)")
assert len(remaining_mod_ids) == 1
print("Suppression multi MODULE ASF OK ✓")

app.destroy()
db.close()
print("\n*** MULTI-SELECT & BULK DELETE OK ***")
