<#
.SYNOPSIS
    Sauvegarde manuelle ou planifiée de Bovo ASF Manager (mode Docker Desktop).

.DESCRIPTION
    Dump PostgreSQL gzip + copie des documents dans un dossier local
    (idéalement pointant vers un NAS BOVO). Prévu pour être exécuté via le
    Planificateur de tâches Windows chaque nuit.

    Rétention configurable (par défaut : 14 archives).

.PARAMETER Destination
    Dossier de destination des archives (peut être un chemin UNC \\NAS\...).

.PARAMETER RetentionCount
    Nombre d'archives à conserver.

.EXAMPLE
    .\backup.ps1 -Destination "\\NAS-BOVO\Sauvegardes\bovo" -RetentionCount 30

    # Créer une tâche planifiée quotidienne à 02:00 :
    schtasks /Create /SC DAILY /ST 02:00 /RL HIGHEST /TN "Bovo Backup" `
      /TR "powershell -ExecutionPolicy Bypass -File C:\Bovo\server\bovo-server\windows\backup.ps1 -Destination D:\Backups\bovo"
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)]
    [string]$Destination,
    [int]$RetentionCount = 14
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Destination)) {
    New-Item -ItemType Directory -Path $Destination -Force | Out-Null
}

$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$archive = Join-Path $Destination "bovo-$stamp.sql.gz"
$docsArchive = Join-Path $Destination "bovo-documents-$stamp.zip"

Write-Host "==> Dump PostgreSQL vers $archive"
# pg_dump | gzip depuis le conteneur, sortie streamée vers un fichier local.
docker exec bovo-db sh -c "pg_dump -U bovo bovo | gzip -9" | Set-Content -Path $archive -Encoding Byte

Write-Host "==> Archive des documents attachés"
$tempDir = Join-Path $env:TEMP "bovo-docs-$stamp"
New-Item -ItemType Directory -Path $tempDir -Force | Out-Null
docker cp bovo-api:/data/documents/. $tempDir
if ((Get-ChildItem $tempDir -Recurse -ErrorAction SilentlyContinue).Count -gt 0) {
    Compress-Archive -Path (Join-Path $tempDir '*') -DestinationPath $docsArchive -CompressionLevel Optimal
} else {
    Write-Host "   Aucun document attaché à archiver."
}
Remove-Item $tempDir -Recurse -Force

Write-Host "==> Purge des archives anciennes (> $RetentionCount)"
Get-ChildItem $Destination -Filter "bovo-*.sql.gz" `
    | Sort-Object CreationTime -Descending `
    | Select-Object -Skip $RetentionCount `
    | Remove-Item -Force
Get-ChildItem $Destination -Filter "bovo-documents-*.zip" `
    | Sort-Object CreationTime -Descending `
    | Select-Object -Skip $RetentionCount `
    | Remove-Item -Force

Write-Host "`n✅ Sauvegarde terminée." -ForegroundColor Green
Write-Host "   DB    : $archive"
if (Test-Path $docsArchive) {
    Write-Host "   Docs  : $docsArchive"
}
