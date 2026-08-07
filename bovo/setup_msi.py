"""Configuration cx_Freeze 8.6.4 pour produire l'installateur MSI Bovo.

Compatible cx_Freeze **8.6.4** / Python **3.13.14**.

Usage (à lancer sur Windows depuis /app/bovo) :

    python setup_msi.py bdist_msi

Produit ``dist/Bovo-<version>-win64.msi`` — un vrai installateur MSI qui :

* installe l'app dans ``C:\\Program Files\\Bovo\\`` (all_users) ;
* crée les raccourcis menu Démarrer + bureau ;
* enregistre l'app dans « Ajouter/Supprimer programmes » ;
* remplace automatiquement les versions plus anciennes via un
  ``upgrade_code`` GUID FIXE (surtout ne pas le changer) ;
* NE TOUCHE JAMAIS à ``%APPDATA%\\Bovo\\`` où sont les données
  utilisateur (paramètres, session, journal).

Les mises à jour se font par ré-installation du même MSI : Windows
Installer détecte l'``upgrade_code``, désinstalle l'ancienne version,
installe la nouvelle. Le contenu de ``%APPDATA%\\Bovo\\`` est conservé
tel quel (situé hors du dossier d'installation).
"""
from __future__ import annotations

import sys
from pathlib import Path

from cx_Freeze import Executable, setup

sys.path.insert(0, str(Path(__file__).parent))
from app.version import __version__  # noqa: E402

APP_ROOT = Path(__file__).resolve().parent

# --- Ressources embarquées (read-only) -------------------------------- #
include_files: list[tuple[str, str]] = []
assets_dir = APP_ROOT / "assets"
if assets_dir.exists():
    # cx_Freeze 8.x : cible relative au build_exe root, sans "/" final.
    include_files.append((str(assets_dir), "assets"))

# --- Options du build_exe --------------------------------------------- #
# cx_Freeze 8.6.4 accepte les mêmes clés que les versions 6.x pour ces
# options de build. Les modules serveur (FastAPI, SQLAlchemy...) sont
# exclus pour maintenir la taille du MSI raisonnable (~60 Mo).
build_exe_options: dict = {
    "packages": [
        "customtkinter", "tkinter", "requests", "sseclient",
        "openpyxl", "fitz",  # PyMuPDF
        "app",               # notre package
    ],
    "excludes": [
        "sqlalchemy", "alembic", "fastapi", "uvicorn", "psycopg", "psycopg_binary",
        "starlette", "IPython", "jedi", "notebook", "test", "unittest",
    ],
    "include_files": include_files,
    "include_msvcr": True,   # embarque le Redistributable Visual C++
    "optimize": 1,
    "silent": False,
}

# --- Options du bdist_msi -------------------------------------------- #
# ATTENTION : upgrade_code EST UN GUID FIXE — ne JAMAIS le changer entre
# deux versions, sinon Windows Installer considère chaque MSI comme une
# app distincte au lieu de remplacer proprement l'ancienne.
UPGRADE_CODE = "{7B9F1E4E-3F16-4E2D-9A8F-1B4C6E2D9A3F}"

icon_ico = assets_dir / "icon.ico"
icon_path = str(icon_ico) if icon_ico.exists() else None

bdist_msi_options: dict = {
    "upgrade_code": UPGRADE_CODE,
    "add_to_path": False,
    "install_icon": icon_path,
    # cx_Freeze 8.x résout ``[ProgramFiles64Folder]`` → C:\Program Files.
    "initial_target_dir": r"[ProgramFiles64Folder]\Bovo",
    "all_users": True,          # installation pour tous les utilisateurs (admin requis)
    "target_name": f"Bovo-{__version__}-win64",  # nom du .msi (sans .msi)
    # Métadonnées Windows Installer (résumé "Propriétés" du .msi).
    "summary_data": {
        "author": "Bovo",
        "comments": "Gestionnaire d'interventions ASF (Inspection ITV)",
        "keywords": "ASF, inspection, ITV, planning, gestion",
    },
}

# --- Exécutable principal --------------------------------------------- #
# En cx_Freeze 8.x, la façon la plus fiable de créer les raccourcis (menu
# Démarrer + Bureau) est de passer ``shortcut_name`` et ``shortcut_dir``
# directement sur l'Executable. On instancie DEUX Executable pointant sur
# le même script (main.py), avec deux ``shortcut_dir`` différents :
#   * ProgramMenuFolder → menu Démarrer
#   * DesktopFolder     → raccourci bureau
# cx_Freeze détectera le doublon binaire et n'embarquera Bovo.exe qu'une
# seule fois dans le MSI (les entrées Shortcut sont dédupliquées).
base = "Win32GUI" if sys.platform == "win32" else None

executables = [
    Executable(
        script="main.py",
        base=base,
        target_name="Bovo.exe",
        icon=icon_path,
        shortcut_name="Bovo ASF Manager",
        shortcut_dir="ProgramMenuFolder",     # menu Démarrer
    ),
    Executable(
        script="main.py",
        base=base,
        target_name="Bovo.exe",
        icon=icon_path,
        shortcut_name="Bovo ASF Manager",
        shortcut_dir="DesktopFolder",         # icône bureau
    ),
]

setup(
    name="Bovo",
    version=__version__,
    description="Bovo ASF Manager — Gestion des inspections ASF (Inspection ITV)",
    author="Bovo",
    options={
        "build_exe": build_exe_options,
        "bdist_msi": bdist_msi_options,
    },
    executables=executables,
)
