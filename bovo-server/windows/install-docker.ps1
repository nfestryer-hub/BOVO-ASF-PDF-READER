<#
.SYNOPSIS
    Installation guidée du serveur Bovo ASF Manager sur Windows (Docker Desktop).

.DESCRIPTION
    Ce script automatise la totalité de l'approche « Docker Desktop » décrite
    dans DEPLOY_WINDOWS.md :

        1. Vérification des prérequis (Windows 10+, exécution en admin).
        2. Installation via winget de Git et Docker Desktop (si absents).
        3. Génération d'un fichier .env sécurisé (JWT_SECRET aléatoire).
        4. Ouverture du port 8000 dans le pare-feu Windows Defender.
        5. Lancement de la pile ``docker compose up -d --build``.
        6. Vérification finale via /api/health.

    À exécuter depuis PowerShell **en tant qu'administrateur** :

        PS> Set-ExecutionPolicy -Scope Process Bypass -Force
        PS> .\install-docker.ps1

.PARAMETER InstallPath
    Dossier racine du projet (défaut : C:\Bovo\server).

.PARAMETER ApiPort
    Port TCP exposé par l'API (défaut : 8000).

.PARAMETER PostgresPassword
    Mot de passe PostgreSQL de la base 'bovo'. Généré aléatoirement si vide.

.PARAMETER AdminPassword
    Mot de passe du compte Admin seedé au premier lancement.

.EXAMPLE
    .\install-docker.ps1 -AdminPassword "ibak23"
#>

[CmdletBinding()]
param(
    [string]$InstallPath = "C:\Bovo\server",
    [int]$ApiPort = 8000,
    [string]$PostgresPassword = "",
    [string]$AdminPassword = "ibak23",
    [string]$AdminUsername = "Bovo"
)

$ErrorActionPreference = "Stop"

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "===> $Message" -ForegroundColor Cyan
}

function Test-Admin {
    $current = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($current)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Error "Ce script doit être exécuté en tant qu'administrateur."
    exit 1
}

# 1. Prérequis
Write-Step "1/6  Vérification des prérequis"
$winVersion = [System.Environment]::OSVersion.Version
Write-Host "Windows $($winVersion.Major).$($winVersion.Minor) build $($winVersion.Build)"

# 2. Installation Git + Docker Desktop
Write-Step "2/6  Installation de Git et Docker Desktop (si nécessaire)"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Installation de Git…"
    winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
} else {
    Write-Host "Git déjà installé : $(git --version)"
}

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Installation de Docker Desktop… (peut prendre 10 min et nécessiter un redémarrage)"
    winget install -e --id Docker.DockerDesktop --accept-package-agreements --accept-source-agreements
    Write-Warning "IMPORTANT : redémarrez le PC pour finaliser l'installation de Docker Desktop,"
    Write-Warning "activez « Start Docker Desktop when you log in », puis relancez ce script."
    exit 0
} else {
    Write-Host "Docker déjà installé : $(docker --version)"
}

# 3. Récupération du code
Write-Step "3/6  Récupération du code (git clone)"
if (-not (Test-Path $InstallPath)) {
    New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
    Set-Location (Split-Path $InstallPath -Parent)
    git clone https://github.com/nfestryer-hub/BOVO-ASF-PDF-READER.git (Split-Path $InstallPath -Leaf)
} else {
    Write-Host "Dossier existant, git pull…"
    Set-Location $InstallPath
    git pull
}

$ServerPath = Join-Path $InstallPath "bovo-server"
Set-Location $ServerPath

# 4. Génération .env
Write-Step "4/6  Génération de la configuration (.env)"

function New-RandomHex {
    param([int]$Bytes = 32)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buffer = New-Object 'System.Byte[]' $Bytes
    $rng.GetBytes($buffer)
    return -join ($buffer | ForEach-Object { $_.ToString("x2") })
}

if ([string]::IsNullOrEmpty($PostgresPassword)) {
    $PostgresPassword = New-RandomHex -Bytes 16
}
$jwtSecret = New-RandomHex -Bytes 32

if (Test-Path .env) {
    Write-Warning ".env existant conservé (aucune modification)"
} else {
    @"
POSTGRES_DB=bovo
POSTGRES_USER=bovo
POSTGRES_PASSWORD=$PostgresPassword

JWT_SECRET=$jwtSecret
ADMIN_USERNAME=$AdminUsername
ADMIN_PASSWORD=$AdminPassword

ALLOWED_ORIGINS=*
ACCESS_TOKEN_MINUTES=480
REFRESH_TOKEN_DAYS=30
API_PORT=$ApiPort

ENVIRONMENT=production
"@ | Set-Content -Path .env -Encoding UTF8
    Write-Host ".env créé — GARDEZ ces identifiants au secret :"
    Write-Host "   Admin   : $AdminUsername / $AdminPassword"
    Write-Host "   Postgres: bovo / $PostgresPassword"
}

# 5. Pare-feu
Write-Step "5/6  Configuration du pare-feu Windows Defender"
$ruleName = "Bovo ASF Manager API ($ApiPort)"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort $ApiPort `
        -Profile Private,Domain | Out-Null
    Write-Host "Règle firewall ajoutée pour le port TCP $ApiPort (Private + Domain)."
} else {
    Write-Host "Règle firewall déjà présente."
}

# 6. Démarrage
Write-Step "6/6  Démarrage de la pile Docker"
docker compose up -d --build

Write-Host ""
Write-Host "En attente du démarrage complet…" -ForegroundColor Yellow
$maxRetries = 30
for ($i = 1; $i -le $maxRetries; $i++) {
    Start-Sleep -Seconds 2
    try {
        $result = Invoke-RestMethod -Uri "http://localhost:$ApiPort/api/health" -TimeoutSec 3
        if ($result.status -eq "ok") {
            Write-Host ""
            Write-Host "✅ Backend opérationnel !" -ForegroundColor Green
            Write-Host "   Version   : $($result.version)"
            $localIp = (Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias "*" -ErrorAction SilentlyContinue `
                | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.*' } `
                | Select-Object -First 1).IPAddress
            if ($localIp) {
                Write-Host "   URL LAN   : http://${localIp}:$ApiPort" -ForegroundColor Green
            }
            Write-Host "   Health    : http://localhost:$ApiPort/api/health"
            Write-Host "   Docs API  : http://localhost:$ApiPort/docs"
            Write-Host ""
            Write-Host "Compte Admin : $AdminUsername / $AdminPassword"
            Write-Host ""
            Write-Host "Pour arrêter : docker compose stop"
            Write-Host "Pour logs    : docker compose logs -f api"
            exit 0
        }
    } catch {
        # Pas encore prêt
    }
    Write-Host -NoNewline "."
}

Write-Host ""
Write-Error "Timeout : le backend n'a pas répondu après $($maxRetries * 2) s."
Write-Host "Consultez les logs : docker compose logs api" -ForegroundColor Yellow
exit 1
