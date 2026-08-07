<#
.SYNOPSIS
    Compile Bovo ASF Manager en MSI (cx_Freeze 8.6.4 / Python 3.13.14).

.DESCRIPTION
    Produit `dist\Bovo-<version>-win64.msi` compatible cx_Freeze 8.6.4.

    ── Cycle de vie ────────────────────────────────────────────────
      1. Bumpe app\version.py (SemVer)
      2. .\build-msi.ps1 -Clean -InstallDeps
      3. .\publish-release.ps1 -Share \\SERVEUR\Partage\Bovo `
                                -MsiUrl http://serveur/updates/Bovo-Setup.msi

    ── Ce que produit le MSI ───────────────────────────────────────
      * installation dans C:\Program Files\Bovo\ (per-machine, admin)
      * raccourcis Bureau + menu Démarrer
      * entrée dans « Ajouter/Supprimer programmes »
      * MAJ sans perte : les données `%APPDATA%\Bovo\` sont préservées

.PARAMETER Clean
    Supprime build\ et dist\ avant de rebuild.

.PARAMETER InstallDeps
    Force la (ré)installation des dépendances Python + cx_Freeze 8.6.4.

.EXAMPLE
    .\build-msi.ps1 -Clean -InstallDeps
    .\build-msi.ps1                    # rebuild rapide, sans réinstall deps
#>

param(
    [switch]$Clean,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Version canonique lue depuis app\version.py (source unique de vérité).
$versionFile = Join-Path $scriptDir "app\version.py"
$content = Get-Content $versionFile -Raw
if ($content -notmatch '__version__\s*=\s*["'']([^"'']+)["'']') {
    Write-Host "❌ Impossible de lire __version__ dans $versionFile" -ForegroundColor Red
    exit 1
}
$version = $matches[1]

Write-Host "=== Build Bovo ASF Manager v$version (MSI, cx_Freeze 8.6.4) ===" -ForegroundColor Cyan

# --- Vérif Python 3.13+ ----------------------------------------------
try {
    $pyVersion = (& python --version 2>&1).ToString()
    Write-Host "Python : $pyVersion" -ForegroundColor Green
    if ($pyVersion -notmatch '3\.(1[3-9]|[2-9]\d)') {
        Write-Host "⚠  Python 3.13+ recommandé (détecté : $pyVersion). Continue quand même." -ForegroundColor Yellow
    }
} catch {
    Write-Host "❌ Python introuvable. Installe Python 3.13+ depuis python.org." -ForegroundColor Red
    exit 1
}

# --- .venv ------------------------------------------------------------
$venv = Join-Path $scriptDir ".venv"
if (-not (Test-Path $venv)) {
    Write-Host "→ Création de l'environnement virtuel .venv..." -ForegroundColor Yellow
    python -m venv .venv
}
& (Join-Path $venv "Scripts\Activate.ps1")

# --- Dépendances ------------------------------------------------------
if ($InstallDeps -or (-not (Test-Path (Join-Path $venv "Scripts\cxfreeze.exe")))) {
    Write-Host "→ Installation des dépendances runtime..." -ForegroundColor Yellow
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt

    Write-Host "→ Installation de cx_Freeze 8.6.4..." -ForegroundColor Yellow
    # Épingle la version exacte demandée par le projet pour éviter les
    # dérives API entre 8.x mineurs.
    python -m pip install "cx_Freeze==8.6.4"
}

# --- Icône .ico à partir du logo PNG (si pas déjà présente) ----------
$icoPath = Join-Path $scriptDir "assets\icon.ico"
$pngPath = Join-Path $scriptDir "assets\logo.png"
if ((-not (Test-Path $icoPath)) -and (Test-Path $pngPath)) {
    Write-Host "→ Génération de assets\icon.ico depuis logo.png..." -ForegroundColor Yellow
    $py = @"
from PIL import Image
img = Image.open(r'$pngPath').convert('RGBA')
img.save(r'$icoPath', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
"@
    python -c $py
}

# --- Icônes PNG (menu / boutons) --------------------------------------
if (Test-Path "app\icons_generator.py") {
    Write-Host "→ Génération des icônes PNG (PIL)..." -ForegroundColor Yellow
    python -m app.icons_generator
}

# --- Nettoyage optionnel ----------------------------------------------
if ($Clean) {
    Write-Host "→ Nettoyage build\ et dist\..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
}

# --- Build MSI --------------------------------------------------------
Write-Host "→ Build MSI (cx_Freeze 8.6.4 bdist_msi)..." -ForegroundColor Yellow
python setup_msi.py bdist_msi

# --- Vérification résultat --------------------------------------------
$msi = Get-ChildItem -Path "dist\*.msi" -ErrorAction SilentlyContinue |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($msi) {
    $sizeMB = [math]::Round($msi.Length / 1MB, 2)

    # SHA256 pour intégrité (également utilisé par l'auto-updater).
    $hash = (Get-FileHash -Algorithm SHA256 -Path $msi.FullName).Hash

    Write-Host ""
    Write-Host "✅ Build réussi !" -ForegroundColor Green
    Write-Host "   Installateur : $($msi.FullName)"
    Write-Host "   Taille       : $sizeMB Mo"
    Write-Host "   SHA256       : $hash"
    Write-Host ""
    Write-Host "📦 Prochaine étape :" -ForegroundColor Cyan
    Write-Host "   .\publish-release.ps1 -Share '\\SERVEUR\Partage\Bovo' `" -ForegroundColor Gray
    Write-Host "                          -MsiUrl 'http://serveur/updates/Bovo-Setup.msi'" -ForegroundColor Gray
} else {
    Write-Host "❌ Build échoué : aucun .msi produit dans dist\" -ForegroundColor Red
    exit 1
}
