@echo off
REM ====================================================================
REM  Bovo ASF Manager — Compilation Windows (.exe)
REM
REM  Utilisation :
REM    build_exe.bat
REM
REM  Le résultat sera dans le dossier `dist\BovoASF\` :
REM    - BovoASF.exe            (l'exécutable principal, double-clic)
REM    - assets\app.ico         (icône Windows — remplaçable !)
REM    - assets\logo.png        (logo BOVO — remplaçable !)
REM    - assets\icons\*.png     (icônes de menu)
REM    - _internal\             (DLL Python, dépendances)
REM
REM  Pour changer l'icône ou le logo APRÈS compilation :
REM    Il suffit de remplacer les fichiers `assets\app.ico` et
REM    `assets\logo.png` dans le dossier `dist\BovoASF\` sans
REM    recompiler. Redémarre BovoASF.exe pour voir la nouvelle image.
REM
REM  Prérequis :
REM    - Python 3.11+ installé et dans le PATH
REM    - pip install -r requirements.txt
REM    - pip install pyinstaller
REM ====================================================================

cd /d "%~dp0"

echo.
echo [1/4] Verification des dependances...
python -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [ERREUR] Impossible d'installer les dependances.
    pause
    exit /b 1
)

echo.
echo [2/4] Installation de PyInstaller (si absent)...
python -m pip install --quiet pyinstaller
if errorlevel 1 (
    echo [ERREUR] Impossible d'installer PyInstaller.
    pause
    exit /b 1
)

echo.
echo [3/4] Nettoyage des anciens builds...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [4/4] Compilation de BovoASF.exe (peut prendre 2-4 minutes)...
python -m PyInstaller --clean --noconfirm bovo.spec
if errorlevel 1 (
    echo [ERREUR] La compilation a echoue.
    pause
    exit /b 1
)

echo.
echo ================================================================
echo   COMPILATION REUSSIE
echo ================================================================
echo.
echo   Executable : dist\BovoASF\BovoASF.exe
echo   Icone      : dist\BovoASF\assets\app.ico  (remplace ce fichier)
echo   Logo       : dist\BovoASF\assets\logo.png (remplace ce fichier)
echo.
echo   Pour distribuer :
echo     - Zippe TOUT le dossier `dist\BovoASF\`
echo     - Envoie le zip a Dylan / au poste terrain
echo     - L'utilisateur decompresse et double-clique BovoASF.exe
echo.
pause
