<#
.SYNOPSIS
    Publie une release Bovo (MSI + latest.json avec SHA256) sur un partage ou un serveur HTTP.

.DESCRIPTION
    Publie l'installateur MSI produit par ``build-msi.ps1`` et génère
    automatiquement ``latest.json`` que l'auto-updater interroge au
    démarrage des postes.

    Le fichier ``latest.json`` respecte le contrat suivant :

        {
          "version":       "1.7.0",
          "msi_url":       "http://serveur/updates/Bovo-Setup.msi",
          "msi_path":      "\\\\SERVEUR\\Partage\\Bovo\\Bovo-Setup.msi",
          "sha256":        "abcdef1234...",
          "size":          62914560,
          "release_notes": "Fix scroll H, multi-select",
          "mandatory":     false,
          "published_at":  "2026-07-30T10:15:00+00:00"
        }

    ── Choix du canal ──────────────────────────────────────────────
    - ``msi_path`` (UNC) : accessible depuis les postes connectés au
      partage réseau. Auto-update via chemin UNC direct.
    - ``msi_url`` (HTTP) : accessible via Internet/VPN. L'auto-updater
      téléchargera le MSI dans %TEMP% puis l'installera silencieusement.
    Les deux peuvent coexister — l'updater privilégie ``msi_url`` s'il est
    accessible, ``msi_path`` sinon.

.PARAMETER Share
    Chemin UNC du dossier de distribution (ex : ``\\SERVEUR\Partage\Bovo``).
    Le MSI + latest.json seront copiés ici.

.PARAMETER MsiUrl
    URL HTTP(S) publique du MSI (ex : ``http://serveur/updates/Bovo-Setup.msi``).
    Écrite telle quelle dans latest.json — la publication effective sur le
    serveur HTTP doit être faite séparément (ce script ne fait pas d'upload
    HTTP, seulement la copie SMB).

.PARAMETER ReleaseNotes
    Notes de version (facultatif).

.PARAMETER Mandatory
    Si présent, la mise à jour bloque l'utilisation avant install.

.PARAMETER KeepArchive
    Archive l'ancien MSI dans ``<Share>\archive\`` avant de le remplacer.

.EXAMPLE
    .\publish-release.ps1 -Share "\\SERVEUR\Partage\Bovo" `
                           -MsiUrl "http://serveur/updates/Bovo-Setup.msi" `
                           -ReleaseNotes "Fix multi-select + colonne ID Ouvrage"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$Share,
    [string]$MsiUrl = "",
    [string]$ReleaseNotes = "",
    [switch]$Mandatory,
    [switch]$KeepArchive
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# --- Version courante -------------------------------------------------
$versionFile = Join-Path $scriptDir "app\version.py"
$content = Get-Content $versionFile -Raw
if ($content -notmatch '__version__\s*=\s*["'']([^"'']+)["'']') {
    Write-Host "❌ Impossible de lire __version__ dans $versionFile" -ForegroundColor Red
    exit 1
}
$version = $matches[1]
Write-Host "Version courante : $version" -ForegroundColor Cyan

# --- MSI local --------------------------------------------------------
$msi = Get-ChildItem -Path "dist\*.msi" -ErrorAction SilentlyContinue |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $msi) {
    Write-Host "❌ Aucun MSI dans dist\. Lance d'abord .\build-msi.ps1" -ForegroundColor Red
    exit 1
}
$sizeMB = [math]::Round($msi.Length / 1MB, 2)
Write-Host "MSI local : $($msi.FullName) ($sizeMB Mo)" -ForegroundColor Green

# --- SHA256 (utilisé par l'auto-updater pour vérifier l'intégrité) --
$sha256 = (Get-FileHash -Algorithm SHA256 -Path $msi.FullName).Hash
Write-Host "SHA256    : $sha256" -ForegroundColor Green

# --- Vérif accès partage ----------------------------------------------
if (-not (Test-Path $Share)) {
    Write-Host "❌ Partage inaccessible : $Share" -ForegroundColor Red
    Write-Host "   Vérifie la connexion réseau et les permissions."
    exit 1
}

# --- Archive optionnelle de l'ancien MSI ------------------------------
$destMsi = Join-Path $Share "Bovo-Setup.msi"
if ($KeepArchive -and (Test-Path $destMsi)) {
    $archiveDir = Join-Path $Share "archive"
    New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
    $oldName = "Bovo-$(Get-Date -Format 'yyyyMMdd-HHmm').msi"
    Copy-Item $destMsi (Join-Path $archiveDir $oldName) -Force
    Write-Host "→ Ancien MSI archivé : $oldName" -ForegroundColor Yellow
}

# --- Copie le nouveau MSI ---------------------------------------------
Copy-Item $msi.FullName $destMsi -Force
Write-Host "→ MSI publié : $destMsi" -ForegroundColor Green

# --- Génération de latest.json ---------------------------------------
$publishedAt = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:sszzz")
$latest = [ordered]@{
    version       = $version
    msi_url       = $MsiUrl
    msi_path      = $destMsi
    sha256        = $sha256.ToLower()
    size          = $msi.Length
    release_notes = $ReleaseNotes
    mandatory     = [bool]$Mandatory
    published_at  = $publishedAt
}

$json = $latest | ConvertTo-Json -Depth 3
$jsonPath = Join-Path $Share "latest.json"
$json | Out-File -FilePath $jsonPath -Encoding UTF8 -Force
Write-Host "→ latest.json généré : $jsonPath" -ForegroundColor Green

Write-Host ""
Write-Host "✅ Release publiée avec succès." -ForegroundColor Cyan
Write-Host ""
Write-Host "Configure les postes utilisateurs (Paramètres > Source des mises à jour) :" -ForegroundColor White
Write-Host "   $jsonPath" -ForegroundColor Gray
if ($MsiUrl) {
    Write-Host ""
    Write-Host "⚠  N'oublie pas de copier $($msi.FullName) sur ton serveur HTTP :" -ForegroundColor Yellow
    Write-Host "   $MsiUrl" -ForegroundColor Gray
}
