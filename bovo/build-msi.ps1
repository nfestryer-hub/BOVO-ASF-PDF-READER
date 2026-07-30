<#
.SYNOPSIS
    Compile Bovo ASF Manager en un installateur MSI Windows (auto-updates via partage réseau).

.DESCRIPTION
    Produit `dist\Bovo-<version>-win64.msi` — un vrai installateur MSI qui :
      * installe l'app dans C:\Program Files\Bovo\
      * crée les raccourcis menu Démarrer + bureau
      * enregistre l'app dans « Ajouter/Supprimer programmes »
      * remplace proprement les versions plus anciennes (via upgrade code fixe)
      * embarque le Redistributable Visual C++

    ── Workflow des mises à jour ──────────────────────────────────────
    1. Sur ton PC dev : bump `app/version.py` (nouveau numéro SemVer)
    2. `.\build-msi.ps1 -Clean -InstallDeps` produit `dist\Bovo-1.7.0-win64.msi`
    3. Copie ce MSI dans le partage réseau :
       Copy-Item dist\Bovo-1.7.0-win64.msi \\SERVEUR\Partage\Bovo\Bovo-Setup.msi -Force
    4. Publie un fichier `latest.json` à côté :
       @{version='1.7.0';msi_path='\\SERVEUR\Partage\Bovo\Bovo-Setup.msi'} | ConvertTo-Json | Out-File latest.json
    5. Chaque poste vérifie ce fichier au démarrage : bandeau "Nouvelle version"
       apparaît, l'utilisateur clique "Installer maintenant" (ou "Plus tard").

    ── Configuration côté utilisateur (à faire une fois) ────────────
    Dans Paramètres → « Source des mises à jour », coller :
      \\SERVEUR\Partage\Bovo\latest.json

.PARAMETER Clean
    Supprime build/ et dist/ avant de rebuild.

.PARAMETER InstallDeps
    Force la (ré)installation des dépendances Python.

.EXAMPLE
    .\build-msi.ps1 -Clean -InstallDeps
#>

param(
    [switch]$Clean,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "=== Build Bovo ASF Manager (MSI installer) ===" -ForegroundColor Cyan

# --- Vérif Python -----------------------------------------------------
try {
    $version = & python --version 2>&1
    Write-Host "Python détecté : $version" -ForegroundColor Green
} catch {
    Write-Host "❌ Python introuvable. Installe Python 3.11+ depuis python.org." -ForegroundColor Red
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
    Write-Host "→ Installation des dépendances + cx_Freeze..." -ForegroundColor Yellow
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    python -m pip install "cx_Freeze>=6.15"
}

# --- Icône PNG → ICO -------------------------------------------------
$icoPath = Join-Path $scriptDir "assets\icon.ico"
$pngPath = Join-Path $scriptDir "assets\logo.png"
if ((-not (Test-Path $icoPath)) -and (Test-Path $pngPath)) {
    Write-Host "→ Génération de assets\icon.ico depuis logo.png..." -ForegroundColor Yellow
    $py = @"
from PIL import Image
img = Image.open(r'$pngPath').convert('RGBA')
img.save(r'$icoPath', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
print('icon.ico OK')
"@
    python -c $py
}

# --- Icônes PNG (menu / boutons) -------------------------------------
if (Test-Path "app\icons_generator.py") {
    Write-Host "→ Génération des icônes PNG (PIL)..." -ForegroundColor Yellow
    python -m app.icons_generator
}

# --- Nettoyage optionnel ----------------------------------------------
if ($Clean) {
    Write-Host "→ Nettoyage des anciens builds..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue build, dist
}

# --- Build MSI --------------------------------------------------------
Write-Host "→ Build MSI (cx_Freeze bdist_msi)..." -ForegroundColor Yellow
python setup_msi.py bdist_msi

# --- Vérification résultat --------------------------------------------
$msi = Get-ChildItem -Path "dist\*.msi" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($msi) {
    $sizeMB = [math]::Round($msi.Length / 1MB, 2)
    Write-Host ""
    Write-Host "✅ Build réussi !" -ForegroundColor Green
    Write-Host "   Installateur : $($msi.FullName)"
    Write-Host "   Taille       : $sizeMB Mo"
    Write-Host ""
    Write-Host "📦 Prochaines étapes :" -ForegroundColor Cyan
    Write-Host "   1. Copie sur le partage :" -ForegroundColor Cyan
    Write-Host "      Copy-Item '$($msi.FullName)' '\\SERVEUR\Partage\Bovo\Bovo-Setup.msi' -Force"
    Write-Host "   2. Publie latest.json :" -ForegroundColor Cyan
    Write-Host "      voir DISTRIBUTION_WINDOWS.md"
} else {
    Write-Host "❌ Build échoué : aucun .msi produit dans dist\" -ForegroundColor Red
    exit 1
}
