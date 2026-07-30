"""Configuration cx_Freeze pour produire un installateur MSI Bovo.

Usage (à lancer sur Windows depuis /app/bovo) :

    python setup_msi.py bdist_msi

Produit ``dist/Bovo-<version>-win64.msi`` — un vrai installateur MSI qui :

* installe l'app dans ``C:\\Program Files\\Bovo\\``
* crée les raccourcis menu Démarrer + bureau
* enregistre l'app dans « Ajouter/Supprimer programmes » (désinstallation propre)
* remplace automatiquement les versions plus anciennes (upgrade code fixe)

Les données utilisateur (SQLite locale, journal, exports, session "Se
souvenir de moi") vont dans ``%APPDATA%\\Bovo\\`` — persistant, indépendant
de l'emplacement d'installation, pas d'écrasement lors des mises à jour.
"""
from __future__ import annotations

import sys
from pathlib import Path

from cx_Freeze import Executable, setup

sys.path.insert(0, str(Path(__file__).parent))
from app.version import __version__

APP_ROOT = Path(__file__).resolve().parent

# --- Ressources embarquées (read-only) -------------------------------- #
include_files: list[tuple[str, str]] = []
assets_dir = APP_ROOT / "assets"
if assets_dir.exists():
    include_files.append((str(assets_dir), "assets"))

# --- Options du build ------------------------------------------------- #
build_exe_options = {
    "packages": [
        "customtkinter", "tkinter", "requests", "sseclient",
        "openpyxl", "fitz",  # PyMuPDF
        "app",  # notre package
    ],
    "excludes": [
        # Modules serveur non nécessaires côté client
        "sqlalchemy", "alembic", "fastapi", "uvicorn", "psycopg", "psycopg_binary",
        "starlette", "IPython", "jedi", "notebook", "test", "unittest",
    ],
    "include_files": include_files,
    "include_msvcr": True,  # embarque le Redistributable Visual C++
    "optimize": 1,
}

# --- Options du MSI --------------------------------------------------- #
# ATTENTION : upgrade_code est un GUID FIXE. Ne le change JAMAIS entre 2
# versions, sinon Windows considère chaque MSI comme une app distincte
# (au lieu de remplacer proprement l'ancienne).
UPGRADE_CODE = "{7B9F1E4E-3F16-4E2D-9A8F-1B4C6E2D9A3F}"

bdist_msi_options = {
    "upgrade_code": UPGRADE_CODE,
    "add_to_path": False,
    "install_icon": str(assets_dir / "icon.ico") if (assets_dir / "icon.ico").exists() else None,
    "initial_target_dir": r"[ProgramFiles64Folder]\Bovo",
    "all_users": True,  # installation pour tous les utilisateurs (nécessite admin)
    "summary_data": {
        "author": "Bovo",
        "comments": "Gestionnaire d'interventions ASF (Inspection ITV)",
        "keywords": "ASF, inspection, ITV, planning, gestion",
    },
    "data": {
        # Shortcuts : menu Démarrer + Bureau
        "Shortcut": [
            (
                "StartMenuShortcut",       # Shortcut
                "ProgramMenuFolder",       # Directory_
                "Bovo ASF Manager",        # Name
                "TARGETDIR",               # Component_
                "[TARGETDIR]Bovo.exe",     # Target
                None,                      # Arguments
                "Gestion des inspections ASF",  # Description
                None, None, None, None,
                "TARGETDIR",               # WkDir
            ),
            (
                "DesktopShortcut",
                "DesktopFolder",
                "Bovo ASF Manager",
                "TARGETDIR",
                "[TARGETDIR]Bovo.exe",
                None,
                "Gestion des inspections ASF",
                None, None, None, None,
                "TARGETDIR",
            ),
        ],
    },
}

# --- Exécutable principal --------------------------------------------- #
icon = str(assets_dir / "icon.ico") if (assets_dir / "icon.ico").exists() else None
bovo_exe = Executable(
    script="main.py",
    base="Win32GUI" if sys.platform == "win32" else None,  # pas de console
    target_name="Bovo.exe",
    icon=icon,
    shortcut_name="Bovo ASF Manager",
    shortcut_dir="ProgramMenuFolder",
    copyright="© Bovo",
)

setup(
    name="Bovo",
    version=__version__,
    description="Bovo ASF Manager — Gestion des inspections ASF (Inspection ITV)",
    author="Bovo",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=[bovo_exe],
)
