<#
.SYNOPSIS
    Compile Bovo ASF Manager en un exécutable Windows autonome (Bovo.exe).

.DESCRIPTION
    Ce script exécute PyInstaller pour produire un unique `Bovo.exe`
    à distribuer sur un partage réseau. Les utilisateurs finaux n'ont
    RIEN à installer (pas de Python, pas de dépendances).

    Pour mettre à jour l'application chez tes utilisateurs :
      1. Lance ce script sur ta machine Windows dev
      2. Copie `dist\Bovo.exe` vers ton partage réseau (écrase l'ancien)
      3. Les utilisateurs récupèrent la nouvelle version au prochain
         lancement, aucune manipulation de leur côté.

    Les données utilisateurs (paramètres, session « Se souvenir de moi »,
    journal local, exports) sont stockées dans %APPDATA%\Bovo\ — PAS à
    côté de l'exe. Un utilisateur peut donc lancer Bovo.exe depuis un
    partage sans droits d'écriture.

.PARAMETER Clean
    Si présent, supprime les dossiers `build/` et `dist/` avant le build.

.PARAMETER InstallDeps
    Si présent, installe/upgrade les dépendances Python avant le build.

.EXAMPLE
    .\build-windows.ps1 -Clean -InstallDeps
    .\build-windows.ps1
#>

param(
    [switch]$Clean,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "=== Build Bovo ASF Manager (Windows onefile) ===" -ForegroundColor Cyan
Write-Host "Répertoire : $scriptDir"

# --- Vérif Python -----------------------------------------------------
$python = "python"
try {
    $version = & $python --version 2>&1
    Write-Host "Python détecté : $version" -ForegroundColor Green
} catch {
    Write-Host "❌ Python introuvable dans le PATH." -ForegroundColor Red
    Write-Host "   Installe Python 3.11+ depuis https://www.python.org/downloads/"
    exit 1
}

# --- Environnement virtuel (recommandé) -------------------------------
$venv = Join-Path $scriptDir ".venv"
if (-not (Test-Path $venv)) {
    Write-Host "→ Création de l'environnement virtuel .venv..." -ForegroundColor Yellow
    & $python -m venv .venv
}

$activateScript = Join-Path $venv "Scripts\Activate.ps1"
Write-Host "→ Activation du .venv" -ForegroundColor Yellow
& $activateScript

# --- Dépendances ------------------------------------------------------
if ($InstallDeps -or (-not (Test-Path (Join-Path $venv "Scripts\pyinstaller.exe")))) {
    Write-Host "→ Installation des dépendances (requirements.txt + pyinstaller)..." -ForegroundColor Yellow
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    python -m pip install pyinstaller
}

# --- Génération des icônes (PIL) --------------------------------------
if (Test-Path "app\icons_generator.py") {
    Write-Host "→ Génération des icônes PNG (PIL)..." -ForegroundColor Yellow
    python -m app.icons_generator
}

# --- Nettoyage optionnel ----------------------------------------------
if ($Clean) {
    Write-Host "→ Nettoyage des anciens builds..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
}

# --- Build PyInstaller ------------------------------------------------
Write-Host "→ Compilation PyInstaller (mode onefile, windowed)..." -ForegroundColor Yellow
pyinstaller bovo.spec --noconfirm

# --- Vérification résultat --------------------------------------------
$exe = Join-Path $scriptDir "dist\Bovo.exe"
if (Test-Path $exe) {
    $sizeMB = [math]::Round((Get-Item $exe).Length / 1MB, 2)
    Write-Host ""
    Write-Host "✅ Build réussi !" -ForegroundColor Green
    Write-Host "   Exécutable : $exe"
    Write-Host "   Taille     : $sizeMB Mo"
    Write-Host ""
    Write-Host "📦 Prochaine étape : copie ce fichier dans ton partage réseau." -ForegroundColor Cyan
    Write-Host "   Ex: Copy-Item '$exe' '\\SERVEUR\Partage\Bovo\Bovo.exe' -Force"
} else {
    Write-Host "❌ Build échoué : Bovo.exe introuvable dans dist\" -ForegroundColor Red
    exit 1
}
