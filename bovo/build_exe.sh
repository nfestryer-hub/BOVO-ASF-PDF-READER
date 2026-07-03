#!/usr/bin/env bash
# ====================================================================
#  Bovo ASF Manager — Compilation Linux/macOS
#
#  Utilisation :
#    ./build_exe.sh
#
#  Sur Linux/macOS ce script produit un binaire natif (pas un .exe).
#  Pour compiler un vrai .exe Windows, exécute build_exe.bat sur un
#  poste Windows.
# ====================================================================
set -eu
cd "$(dirname "$0")"

echo "[1/4] Vérification des dépendances Python…"
python3 -m pip install --quiet -r requirements.txt

echo "[2/4] Installation de PyInstaller…"
python3 -m pip install --quiet pyinstaller

echo "[3/4] Nettoyage des anciens builds…"
rm -rf build dist

echo "[4/4] Compilation (peut prendre 2-4 minutes)…"
python3 -m PyInstaller --clean --noconfirm bovo.spec

echo
echo "================================================================"
echo "  COMPILATION TERMINÉE"
echo "================================================================"
echo
echo "  Exécutable : dist/BovoASF/BovoASF"
echo "  Icône      : dist/BovoASF/assets/app.ico  (remplace ce fichier)"
echo "  Logo       : dist/BovoASF/assets/logo.png (remplace ce fichier)"
echo
