<#
.SYNOPSIS
    Vérifie l'état du serveur Bovo ASF Manager (Docker ou natif).

.DESCRIPTION
    Diagnostic rapide à exécuter en cas de problème. Affiche :

    - Statut des services (conteneurs Docker ou Windows Service)
    - Réponse de /api/health
    - Adresse IP locale à communiquer aux clients
    - Dernières lignes de log
    - Espace disque restant

.EXAMPLE
    .\status.ps1
#>

[CmdletBinding()]
param(
    [int]$ApiPort = 8000
)

Write-Host "=== Bovo ASF Manager — Diagnostic ===" -ForegroundColor Cyan
Write-Host "Date : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

Write-Host "`n--- Réseau ---"
$ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue `
    | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.*' }
$ips | Select-Object IPAddress, InterfaceAlias | Format-Table

Write-Host "--- Health API ---"
try {
    $r = Invoke-RestMethod -Uri "http://localhost:$ApiPort/api/health" -TimeoutSec 3
    Write-Host "✅ Backend OK — version $($r.version)" -ForegroundColor Green
} catch {
    Write-Host "❌ Backend injoignable sur le port $ApiPort" -ForegroundColor Red
    Write-Host "   Détail : $($_.Exception.Message)"
}

Write-Host "`n--- Docker (si applicable) ---"
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose ps 2>$null
} else {
    Write-Host "docker non installé (mode natif)."
}

Write-Host "`n--- Service Windows 'BovoASFManager' (si natif) ---"
$svc = Get-Service BovoASFManager -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "$($svc.Name) : $($svc.Status)"
} else {
    Write-Host "Aucun service natif enregistré (probablement mode Docker)."
}

Write-Host "`n--- PostgreSQL Windows Service (si natif) ---"
Get-Service -DisplayName "postgresql*" -ErrorAction SilentlyContinue `
    | Select-Object Status, Name, DisplayName | Format-Table

Write-Host "--- Dernières logs API ---"
if (Get-Command docker -ErrorAction SilentlyContinue) {
    docker compose logs --tail=20 api 2>$null
}

Write-Host "`n--- Espace disque C: ---"
Get-PSDrive C | Select-Object Used, Free, @{n='Free (GB)';e={[math]::Round($_.Free/1GB,1)}} | Format-Table
