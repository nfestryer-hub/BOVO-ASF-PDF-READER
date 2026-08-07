# -*- mode: python ; coding: utf-8 -*-
"""Spec PyInstaller pour Bovo ASF Manager (Windows onefile).

Regroupe l'app CustomTkinter + assets (logo, icônes) + dépendances runtime
(customtkinter, pymupdf, openpyxl, requests, sseclient-py) dans un unique
`Bovo.exe` distribuable sur un partage réseau.

Build : `pyinstaller bovo.spec` (à lancer depuis /app/bovo sur Windows).
"""
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

APP_ROOT = Path(SPECPATH).resolve()

# --- Données à embarquer (read-only) ---------------------------------- #
datas: list[tuple[str, str]] = []

# Assets internes de l'app (logo, icônes générées par PIL, etc.)
assets_dir = APP_ROOT / "assets"
if assets_dir.exists():
    datas.append((str(assets_dir), "assets"))

# customtkinter embarque ses propres ressources JSON/thèmes
datas += collect_data_files("customtkinter")

# tkcalendar (utilisé pour les sélecteurs de date) — au cas où
try:
    datas += collect_data_files("tkcalendar")
except Exception:  # noqa: BLE001 — optionnel
    pass

# --- Modules cachés (imports dynamiques) ------------------------------ #
hiddenimports: list[str] = []
hiddenimports += collect_submodules("customtkinter")
# PyMuPDF sous-modules parfois non détectés par l'analyse statique
hiddenimports += ["fitz", "fitz.utils"]
# sseclient-py (import dynamique via requests)
hiddenimports += ["sseclient"]
# psycopg (au cas où — surtout pour version future serveur embarqué)
hiddenimports += []


block_cipher = None

a = Analysis(
    ["main.py"],
    pathex=[str(APP_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Modules serveur non nécessaires côté client desktop
        "sqlalchemy", "alembic", "fastapi", "uvicorn", "psycopg",
        "psycopg_binary", "starlette", "pydantic_core.pydantic",
        # Frameworks web front non utilisés
        "IPython", "jedi", "notebook",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# Icône Windows (fichier .ico dans assets/) si présent
icon_path = APP_ROOT / "assets" / "icon.ico"
icon_arg = str(icon_path) if icon_path.exists() else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Bovo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # compresse le binaire (UPX doit être dans le PATH ; sinon ignoré)
    upx_exclude=[
        # UPX corrompt parfois certaines DLLs Windows critiques
        "vcruntime140.dll", "python3.dll", "python311.dll",
    ],
    runtime_tmpdir=None,
    console=False,      # pas de fenêtre CMD noire (mode --windowed)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_arg,
    version=None,       # possible d'ajouter un version_info.txt pour signature/props
)
