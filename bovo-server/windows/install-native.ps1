<#
.SYNOPSIS
    Installation guidée du serveur Bovo ASF Manager sur Windows (mode natif).

.DESCRIPTION
    Mode alternatif à Docker Desktop : installe Python 3.12, PostgreSQL 16,
    NSSM et configure un service Windows qui démarre AVANT toute session
    utilisateur — idéal pour un serveur headless.

    Étapes :

        1. Vérification administrateur
        2. Installation via winget (Python, PostgreSQL, NSSM, Git si absents)
        3. Création de la base 'bovo' + utilisateur applicatif
        4. Création du virtualenv Python + pip install
        5. Génération sécurisée du .env
        6. Enregistrement du service Windows 'BovoASFManager' via NSSM
        7. Ouverture du pare-feu + démarrage du service
        8. Health check

    À exécuter en administrateur :

        PS> Set-ExecutionPolicy -Scope Process Bypass -Force
        PS> .\install-native.ps1 -PostgresSuperPassword "PostgresRoot!" `
                                 -AdminPassword "ibak23"
#>

[CmdletBinding()]
param(
    [string]$InstallPath = "C:\Bovo\server",
    [int]$ApiPort = 8000,
    [Parameter(Mandatory=$true)]
    [string]$PostgresSuperPassword,
    [string]$BovoDbPassword = "",
    [string]$AdminUsername = "Bovo",
    [string]$AdminPassword = "ibak23"
)

$ErrorActionPreference = "Stop"

function Test-Admin {
    $c = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal($c)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}
if (-not (Test-Admin)) {
    Write-Error "Ce script doit être exécuté en tant qu'administrateur."
    exit 1
}

function Write-Step { param($m) Write-Host "`n===> $m" -ForegroundColor Cyan }
function New-RandomHex {
    param([int]$Bytes = 16)
    $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    $buffer = New-Object 'System.Byte[]' $Bytes
    $rng.GetBytes($buffer)
    return -join ($buffer | ForEach-Object { $_.ToString("x2") })
}

if ([string]::IsNullOrEmpty($BovoDbPassword)) { $BovoDbPassword = New-RandomHex 16 }
$jwtSecret = New-RandomHex 32

# 1. Installation binaires
Write-Step "1/8  Installation des dépendances système via winget"
$packages = @{
    "Git"        = "Git.Git"
    "Python 3.12"= "Python.Python.3.12"
    "PostgreSQL" = "PostgreSQL.PostgreSQL"
    "NSSM"       = "NSSM.NSSM"
}
foreach ($name in $packages.Keys) {
    $id = $packages[$name]
    Write-Host "  → $name..."
    winget install -e --id $id --accept-package-agreements --accept-source-agreements | Out-Null
}
$env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
            [Environment]::GetEnvironmentVariable("Path","User")

# 2. Récupération du code
Write-Step "2/8  Récupération du code"
if (-not (Test-Path $InstallPath)) {
    New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
    Set-Location (Split-Path $InstallPath -Parent)
    git clone https://github.com/nfestryer-hub/BOVO-ASF-PDF-READER.git (Split-Path $InstallPath -Leaf)
}
$ServerPath = Join-Path $InstallPath "bovo-server"
Set-Location $ServerPath

# 3. Setup PostgreSQL
Write-Step "3/8  Création de la base 'bovo' et de l'utilisateur applicatif"
$psql = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\psql.exe" | Select-Object -First 1
if (-not $psql) { Write-Error "psql.exe introuvable. Vérifiez l'installation PostgreSQL."; exit 1 }
$env:PGPASSWORD = $PostgresSuperPassword

& $psql.FullName -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='bovo'" `
    | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Error "Impossible de se connecter à Postgres."; exit 1 }

& $psql.FullName -U postgres -c "CREATE DATABASE bovo;" 2>&1 | Out-Null
& $psql.FullName -U postgres -c "CREATE USER bovo WITH PASSWORD '$BovoDbPassword';" 2>&1 | Out-Null
& $psql.FullName -U postgres -c "ALTER USER bovo WITH PASSWORD '$BovoDbPassword';" | Out-Null
& $psql.FullName -U postgres -d bovo -c "GRANT ALL ON SCHEMA public TO bovo;" | Out-Null
& $psql.FullName -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE bovo TO bovo;" | Out-Null
Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue

# 4. Virtualenv Python
Write-Step "4/8  Création du virtualenv + installation des dépendances Python"
python -m venv .venv
& ".\.venv\Scripts\python.exe" -m pip install --upgrade pip
& ".\.venv\Scripts\pip.exe" install -r requirements.txt

# 5. Fichier .env
Write-Step "5/8  Génération du fichier .env"
if (-not (Test-Path .env)) {
    @"
POSTGRES_DSN=postgresql+psycopg://bovo:$BovoDbPassword@localhost:5432/bovo
JWT_SECRET=$jwtSecret
ADMIN_USERNAME=$AdminUsername
ADMIN_PASSWORD=$AdminPassword
ALLOWED_ORIGINS=*
ACCESS_TOKEN_MINUTES=480
REFRESH_TOKEN_DAYS=30
ENVIRONMENT=production
"@ | Set-Content .env -Encoding UTF8
}

# 6. Service Windows via NSSM
Write-Step "6/8  Enregistrement du service Windows 'BovoASFManager'"
$serviceName = "BovoASFManager"
$uvicorn = Join-Path $ServerPath ".venv\Scripts\uvicorn.exe"
if (Get-Service $serviceName -ErrorAction SilentlyContinue) {
    nssm stop $serviceName confirm | Out-Null
    nssm remove $serviceName confirm | Out-Null
}
nssm install $serviceName $uvicorn "app.main:app --host 0.0.0.0 --port $ApiPort" | Out-Null
nssm set $serviceName AppDirectory $ServerPath | Out-Null
nssm set $serviceName Start SERVICE_AUTO_START | Out-Null
nssm set $serviceName AppRestartDelay 5000 | Out-Null
nssm set $serviceName AppStdout (Join-Path $ServerPath "logs\uvicorn.out.log") | Out-Null
nssm set $serviceName AppStderr (Join-Path $ServerPath "logs\uvicorn.err.log") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $ServerPath "logs") -Force | Out-Null

# Variables d'environnement chargées via python-dotenv (lit .env) — rien à
# ajouter côté nssm si on utilise Pydantic Settings ; ok par défaut.

# 7. Pare-feu
Write-Step "7/8  Ouverture du port $ApiPort dans le pare-feu Windows Defender"
$ruleName = "Bovo ASF Manager API ($ApiPort)"
if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName $ruleName `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort $ApiPort `
        -Profile Private,Domain | Out-Null
}

# 8. Démarrage + health
Write-Step "8/8  Démarrage du service et vérification"
nssm start $serviceName | Out-Null
Start-Sleep -Seconds 3
for ($i = 1; $i -le 20; $i++) {
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:$ApiPort/api/health" -TimeoutSec 3
        if ($health.status -eq "ok") {
            Write-Host "`n✅ Service 'BovoASFManager' démarré (v$($health.version))" -ForegroundColor Green
            Write-Host "   Il redémarrera automatiquement à chaque boot Windows."
            $localIp = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue `
                | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.*' } `
                | Select-Object -First 1).IPAddress
            if ($localIp) {
                Write-Host "   URL LAN : http://${localIp}:$ApiPort" -ForegroundColor Green
            }
            Write-Host "`nIdentifiants :"
            Write-Host "   Admin API  : $AdminUsername / $AdminPassword"
            Write-Host "   PostgreSQL : bovo / $BovoDbPassword (à conserver)"
            exit 0
        }
    } catch { }
    Start-Sleep -Seconds 2
    Write-Host -NoNewline "."
}

Write-Error "`nTimeout : le service n'a pas répondu."
Write-Host "Consultez : $ServerPath\logs\uvicorn.err.log" -ForegroundColor Yellow
exit 1
