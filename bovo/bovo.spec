# -*- mode: python ; coding: utf-8 -*-
"""Configuration PyInstaller pour Bovo ASF Manager.

Génère un exécutable Windows `.exe` avec :
  * Icône Windows personnalisée (``assets/app.ico``)
  * Logo embarqué (``assets/logo.png``)
  * Toutes les icônes SVG/PNG du dossier ``assets/icons/``
  * Toutes les dépendances CustomTkinter, PyMuPDF, openpyxl, bcrypt, etc.

**Personnalisation icône / logo** (sans recompiler)
---------------------------------------------------
Après compilation, le dossier ``dist/BovoASF/`` contient l'exécutable et
un sous-dossier ``assets/``. Pour changer l'icône ou le logo :

  1. Remplace ``dist/BovoASF/assets/app.ico`` par ton propre .ico
  2. Remplace ``dist/BovoASF/assets/logo.png`` par ton propre PNG
  3. Relance ``BovoASF.exe`` — pas besoin de recompiler.

**Build**
---------
Sur Windows :

    pyinstaller --clean --noconfirm bovo.spec

Sur Linux/macOS (croisé — pour tester la structure sans exe Windows) :

    pyinstaller --clean --noconfirm bovo.spec

Le résultat sera dans ``dist/BovoASF/BovoASF`` (ou ``.exe`` sous Windows).
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all  # noqa: F401

# Racine du projet (l'endroit où se trouve ce spec file).
BASE_DIR = Path(SPECPATH)  # noqa: F821 - fourni par PyInstaller
ASSETS_DIR = BASE_DIR / "assets"
ICON_FILE = ASSETS_DIR / "app.ico"

# ------------------------------------------------------------------ #
# CustomTkinter embarque des thèmes JSON + polices TTF qu'il faut copier
# manuellement (PyInstaller ne les détecte pas via l'import statique).
# ------------------------------------------------------------------ #
ctk_datas, ctk_binaries, ctk_hiddenimports = collect_all("customtkinter")
pil_datas, pil_binaries, pil_hiddenimports = collect_all("PIL")

# ------------------------------------------------------------------ #
# Ressources à inclure (assets bundlés) — copiés dans dist/BovoASF/assets/
# ------------------------------------------------------------------ #
datas = [
    (str(ASSETS_DIR / "logo.png"), "assets"),
    (str(ASSETS_DIR / "app.ico"), "assets"),
    (str(ASSETS_DIR / "icons"), "assets/icons"),
    *ctk_datas,
    *pil_datas,
]

# Modules cachés que PyInstaller n'arrive pas toujours à détecter tout seul.
hiddenimports = [
    "customtkinter",
    "tkinter",
    "PIL._tkinter_finder",
    "fitz",
    "openpyxl",
    "bcrypt",
    "requests",
    "sseclient",
    "reportlab",
    "reportlab.pdfgen.canvas",
    "reportlab.lib",
    *ctk_hiddenimports,
    *pil_hiddenimports,
]

binaries = [*ctk_binaries, *pil_binaries]

a = Analysis(  # noqa: F821 - PyInstaller runtime scope
    ["main.py"],
    pathex=[str(BASE_DIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Modules lourds inutiles côté client (économise ~30 MB).
        "matplotlib", "numpy.f2py", "pandas.tests", "IPython",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BovoASF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,               # ← mode fenêtre (pas de terminal noir)
    disable_windowed_traceback=False,
    icon=str(ICON_FILE) if ICON_FILE.exists() else None,
    version=None,
    # ``contents_directory='.'`` place les DLL Python à côté du .exe au
    # lieu du dossier ``_internal/``. Ainsi, la structure est plate :
    #     dist/BovoASF/
    #       BovoASF.exe
    #       assets/     ← icône & logo personnalisables ici
    #       *.dll, *.pyd  (dépendances)
    # L'utilisateur voit tout de suite le dossier ``assets/`` sans avoir
    # à explorer ``_internal/`` pour retrouver son logo.
    contents_directory=".",
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BovoASF",
)
