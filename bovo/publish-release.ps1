<#
.SYNOPSIS
    Publie une nouvelle version Bovo ASF Manager sur un partage réseau.

.DESCRIPTION
    Copie le MSI généré par build-msi.ps1 vers le partage réseau et
    génère un fichier latest.json que l'auto-updater interroge au
    démarrage des postes utilisateurs.

.PARAMETER Share
    Chemin UNC du dossier de distribution (ex : \\SERVEUR\Partage\Bovo).

.PARAMETER ReleaseNotes
    Notes de version (facultatif) affichées à l'utilisateur.

.PARAMETER Mandatory
    Si présent, la mise à jour est obligatoire (bloque le démarrage).

.PARAMETER KeepArchive
    Archive l'ancien MSI dans `<Share>\archive\` avant de le remplacer.

.EXAMPLE
    .\publish-release.ps1 -Share "\\SERVEUR\Partage\Bovo" `
                           -ReleaseNotes "Fix scroll H, colonne ID Ouvrage"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$Share,
    [string]$ReleaseNotes = "",
    [switch]$Mandatory,
    [switch]$KeepArchive
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

# Lit la version courante depuis app\version.py
$versionFile = Join-Path $scriptDir "app\version.py"
$content = Get-Content $versionFile -Raw
if ($content -notmatch '__version__\s*=\s*["'']([^"'']+)["'']') {
    Write-Host "❌ Impossible de lire __version__ dans $versionFile" -ForegroundColor Red
    exit 1
}
$version = $matches[1]
Write-Host "Version courante : $version" -ForegroundColor Cyan

# Cherche le MSI produit par build-msi.ps1
$msi = Get-ChildItem -Path "dist\*.msi" -ErrorAction SilentlyContinue |
       Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $msi) {
    Write-Host "❌ Aucun MSI trouvé dans dist\. Lance d'abord .\build-msi.ps1" -ForegroundColor Red
    exit 1
}
Write-Host "MSI local : $($msi.FullName) ($([math]::Round($msi.Length/1MB,2)) Mo)" -ForegroundColor Green

# Vérifie l'accès au partage
if (-not (Test-Path $Share)) {
    Write-Host "❌ Partage inaccessible : $Share" -ForegroundColor Red
    Write-Host "   Vérifie la connexion réseau et les permissions."
    exit 1
}

# Archive l'ancien MSI si demandé
$destMsi = Join-Path $Share "Bovo-Setup.msi"
if ($KeepArchive -and (Test-Path $destMsi)) {
    $archiveDir = Join-Path $Share "archive"
    New-Item -ItemType Directory -Path $archiveDir -Force | Out-Null
    $oldName = "Bovo-$(Get-Date -Format 'yyyyMMdd-HHmm').msi"
    Copy-Item $destMsi (Join-Path $archiveDir $oldName) -Force
    Write-Host "→ Ancien MSI archivé : $oldName" -ForegroundColor Yellow
}

# Copie le nouveau MSI
Copy-Item $msi.FullName $destMsi -Force
Write-Host "→ MSI publié : $destMsi" -ForegroundColor Green

# Génère latest.json
$latest = [PSCustomObject]@{
    version       = $version
    msi_path      = $destMsi
    release_notes = $ReleaseNotes
    mandatory     = [bool]$Mandatory
    published_at  = (Get-Date -Format "yyyy-MM-ddTHH:mm:sszzz")
}
$json = $latest | ConvertTo-Json -Depth 3
$jsonPath = Join-Path $Share "latest.json"
$json | Out-File -FilePath $jsonPath -Encoding UTF8 -Force
Write-Host "→ latest.json généré : $jsonPath" -ForegroundColor Green
Write-Host ""
Write-Host "✅ Release publiée avec succès." -ForegroundColor Cyan
Write-Host ""
Write-Host "Les utilisateurs verront le bandeau de mise à jour au prochain lancement." -ForegroundColor White
Write-Host "Assure-toi qu'ils ont configuré la source dans Paramètres :" -ForegroundColor White
Write-Host "   $jsonPath" -ForegroundColor Gray
