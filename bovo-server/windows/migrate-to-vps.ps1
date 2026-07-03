<#
.SYNOPSIS
    Migration à froid du serveur Bovo ASF Manager (Windows → VPS).

.DESCRIPTION
    Produit une archive complète (base + documents + .env) prête à être
    téléversée sur un VPS Linux. Aucune modification de code : sur le VPS,
    ``docker compose up -d`` puis restauration.

    Sortie : un fichier zip unique dans C:\Bovo\migration\bovo-<date>.zip

.EXAMPLE
    .\migrate-to-vps.ps1
    # Puis, sur le VPS Linux :
    #   scp bovo-2026-07-01.zip user@vps:/tmp/
    #   unzip /tmp/bovo-*.zip -d /opt/bovo/
    #   cd /opt/bovo/server/bovo-server
    #   docker compose up -d --build
    #   docker compose exec -T db psql -U bovo -d bovo < /opt/bovo/dump.sql
    #   docker cp /opt/bovo/documents bovo-api:/data/
#>

[CmdletBinding()]
param(
    [string]$InstallPath = "C:\Bovo\server",
    [string]$OutputPath = "C:\Bovo\migration"
)

$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$stageDir = Join-Path $env:TEMP "bovo-migrate-$stamp"
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null
New-Item -ItemType Directory -Path $OutputPath -Force | Out-Null

Write-Host "==> 1. Copie du code + .env" -ForegroundColor Cyan
Copy-Item -Path (Join-Path $InstallPath "bovo-server") -Destination (Join-Path $stageDir "bovo-server") `
    -Recurse -Exclude "logs", ".venv", "__pycache__"

Write-Host "==> 2. Dump PostgreSQL"
$dumpPath = Join-Path $stageDir "dump.sql"
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker exec bovo-db pg_dump -U bovo bovo > $dumpPath
} else {
    $psql = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\pg_dump.exe" | Select-Object -First 1
    if (-not $psql) { Write-Error "pg_dump.exe introuvable."; exit 1 }
    $env:PGPASSWORD = Read-Host "Mot de passe DB 'bovo'"
    & $psql.FullName -U bovo bovo | Set-Content $dumpPath
    Remove-Item Env:PGPASSWORD
}

Write-Host "==> 3. Copie des documents attachés"
if (Get-Command docker -ErrorAction SilentlyContinue) {
    New-Item -ItemType Directory -Path (Join-Path $stageDir "documents") -Force | Out-Null
    docker cp bovo-api:/data/documents/. (Join-Path $stageDir "documents")
}

Write-Host "==> 4. Génération de l'archive zip"
$archive = Join-Path $OutputPath "bovo-migration-$stamp.zip"
Compress-Archive -Path (Join-Path $stageDir '*') -DestinationPath $archive -CompressionLevel Optimal

Remove-Item $stageDir -Recurse -Force

Write-Host "`n✅ Archive prête à transférer :" -ForegroundColor Green
Write-Host "   $archive"
Write-Host "`nSur le VPS :`n"
Write-Host "  scp `"$archive`" user@vps:/tmp/"
Write-Host "  ssh user@vps"
Write-Host "  unzip /tmp/$(Split-Path $archive -Leaf) -d /opt/bovo"
Write-Host "  cd /opt/bovo/bovo-server"
Write-Host "  docker compose up -d --build"
Write-Host "  docker compose exec -T db psql -U bovo -d bovo < /opt/bovo/dump.sql"
Write-Host "  docker cp /opt/bovo/documents bovo-api:/data/"
