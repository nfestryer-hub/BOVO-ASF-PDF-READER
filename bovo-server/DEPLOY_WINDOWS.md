# Déploiement Windows — Bovo ASF Manager Server

Ce guide décrit deux façons d'installer le backend sur un poste Windows du
réseau BOVO (celui qui reste allumé en permanence). **La méthode Docker
Desktop est recommandée** car elle garantit un fonctionnement 100 %
identique à un VPS futur (aucune modification de code, mêmes commandes).

- [Prérequis communs](#prérequis-communs)
- [🥇 Approche 1 — Docker Desktop (recommandée)](#approche-1--docker-desktop-recommandée)
- [Approche 2 — Installation native](#approche-2--installation-native-python--postgresql-windows)
- [Ouverture du réseau BOVO](#ouverture-du-réseau-bovo)
- [Sauvegardes & maintenance](#sauvegardes--maintenance)
- [Migration ultérieure vers un VPS](#migration-ultérieure-vers-un-vps)

---

## Prérequis communs

1. **Windows 10 22H2 / Windows 11 / Windows Server 2019+**, 64 bits.
2. **8 Go de RAM minimum**, 20 Go d'espace libre sur `C:`.
3. **Adresse IP statique** attribuée par le routeur BOVO (essentiel : les
   clients desktop doivent pointer vers une IP stable).
4. **Ouverture Windows Defender** du port choisi (voir plus bas).
5. **Session Windows dédiée** (recommandé) : créer un utilisateur
   `bovo-server` avec droits Admin locaux et **connexion automatique
   activée** (`netplwiz` → décocher « Les utilisateurs doivent entrer un nom
   d'utilisateur… »). Nécessaire pour Docker Desktop qui démarre par session
   utilisateur.

---

## Approche 1 — Docker Desktop (recommandée)

### 1.1 Installation

1. Télécharger **Docker Desktop pour Windows** :
   <https://www.docker.com/products/docker-desktop/>
2. Installer avec les options par défaut (WSL 2 activé automatiquement).
3. Au premier lancement :
   - Accepter la licence gratuite Personal / Small Business (BOVO ≤ 250
     employés et ≤ 10 M$ CA → licence gratuite).
   - **Settings → General → « Start Docker Desktop when you log in »** ✅.
   - Settings → Resources : allouer au moins **4 Go RAM** et 2 CPU.

### 1.2 Récupération du code

Ouvrir PowerShell (en session `bovo-server`) et exécuter :

```powershell
# Installer Git s'il n'est pas déjà présent
winget install -e --id Git.Git

# Créer le dossier BOVO et cloner (ou copier via clé USB)
mkdir C:\Bovo
cd C:\Bovo
git clone https://github.com/nfestryer-hub/BOVO-ASF-PDF-READER.git server
cd server\bovo-server
```

### 1.3 Configuration

```powershell
# Copier le modèle et générer un secret fort
Copy-Item .env.example .env

# Générer un JWT secret (32 octets hex — 64 caractères)
$jwt = -join ((48..57) + (97..102) | Get-Random -Count 64 | %{[char]$_})
(Get-Content .env) -replace 'remplacez-par-openssl-rand-hex-32', $jwt | Set-Content .env

# Ouvrir le .env dans Notepad et personnaliser POSTGRES_PASSWORD + ADMIN_PASSWORD
notepad .env
```

### 1.4 Démarrage

```powershell
docker compose up -d --build
docker compose ps            # vérifier : bovo-db, bovo-api, bovo-backup = Up
docker compose logs -f api   # attendre "Serveur prêt"
```

Tester depuis un autre PC du réseau :

```powershell
# Depuis le PC serveur — récupérer l'IP locale
ipconfig | Select-String IPv4

# Depuis un client (remplacer 192.168.1.42 par l'IP du serveur)
curl http://192.168.1.42:8000/api/health
```

### 1.5 Auto-démarrage au boot

Deux couches :

1. **Docker Desktop** démarre automatiquement à la connexion Windows (cf. §1.1).
2. **Les conteneurs** ont `restart: unless-stopped` dans `docker-compose.yml`
   → Docker les relance automatiquement.

Résultat : Windows démarre → session `bovo-server` ouverte → Docker Desktop
démarre → conteneurs `bovo-db` + `bovo-api` + `bovo-backup` démarrent.

**Pour tester** : redémarrer le PC, attendre 2 minutes, `curl` le health
endpoint depuis un autre poste.

> **Note importante** : Docker Desktop nécessite une session utilisateur
> ouverte. Si le PC est verrouillé (Ctrl+L), les conteneurs continuent de
> tourner. Si personne n'est connecté, ils ne démarrent pas. C'est pourquoi
> on active la **connexion automatique** de la session `bovo-server`.

---

## Approche 2 — Installation native (Python + PostgreSQL Windows)

Utile si vous ne pouvez pas installer Docker Desktop (Windows Home < 2004,
ou politique interne interdisant WSL 2). Plus complexe à maintenir mais
fonctionne également.

### 2.1 Installer PostgreSQL 16

1. Télécharger l'installeur officiel :
   <https://www.postgresql.org/download/windows/>
2. Installer avec :
   - Password superuser `postgres` : notez-le.
   - Port `5432` (par défaut).
   - Locale `Default`.
3. PostgreSQL s'installe automatiquement comme **service Windows**
   (`postgresql-x64-16`), démarrage automatique au boot.

Créer la base :

```powershell
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE DATABASE bovo;"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "CREATE USER bovo WITH PASSWORD 'ChangezMoi';"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -d bovo -c "GRANT ALL ON SCHEMA public TO bovo;"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE bovo TO bovo;"
```

### 2.2 Installer Python 3.12 + le backend

```powershell
winget install -e --id Python.Python.3.12
# Fermer et rouvrir PowerShell pour recharger le PATH.

cd C:\Bovo\server\bovo-server
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Créer le fichier `.env` (identique à l'approche Docker, mais avec le DSN
local) :

```
POSTGRES_DSN=postgresql+psycopg://bovo:ChangezMoi@localhost:5432/bovo
JWT_SECRET=... (généré aléatoirement)
ADMIN_USERNAME=Bovo
ADMIN_PASSWORD=ibak23
```

Test manuel :

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Ctrl+C pour arrêter après vérification.
```

### 2.3 Auto-démarrage via NSSM (Windows Service)

**NSSM** (Non-Sucking Service Manager) transforme un exécutable en service
Windows qui démarre **avant** l'ouverture de session.

```powershell
# Installer NSSM
winget install -e --id NSSM.NSSM

# Créer le service (interactive)
nssm install BovoASFManager
# → Path      : C:\Bovo\server\bovo-server\.venv\Scripts\uvicorn.exe
# → Arguments : app.main:app --host 0.0.0.0 --port 8000
# → Startup dir : C:\Bovo\server\bovo-server
# Onglet "Environment" : coller les variables du .env (POSTGRES_DSN, JWT_SECRET, etc.)
# Onglet "Startup" : "Automatic"

# Démarrer le service
nssm start BovoASFManager

# Vérifier
Get-Service BovoASFManager
curl http://localhost:8000/api/health
```

Le service redémarre automatiquement en cas de crash (`nssm set
BovoASFManager AppRestartDelay 5000`) et se lance au démarrage de Windows,
**même sans utilisateur connecté**.

---

## Ouverture du réseau BOVO

Ouvrir le port 8000 (ou celui choisi) dans le pare-feu Windows Defender :

```powershell
# Depuis PowerShell en Administrateur
New-NetFirewallRule -DisplayName "Bovo ASF Manager API" `
    -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 `
    -Profile Private,Domain
```

**Ne PAS ouvrir le port sur Internet public** sans reverse proxy TLS. Le
réseau BOVO interne suffit tant que tous les postes clients y sont
connectés (VPN si distant).

---

## Sauvegardes & maintenance

### Docker Desktop

Les sauvegardes tournent automatiquement dans le conteneur `bovo-backup`
(pg_dump quotidien gzip, rétention 14 jours). Récupérer une archive :

```powershell
# Lister les backups
docker exec bovo-backup ls -la /backups

# Copier localement (ex. vers un NAS BOVO)
docker cp bovo-backup:/backups C:\Bovo\backups
```

Automatiser la copie vers un NAS via **Planificateur de tâches Windows** —
créer une tâche « BOVO backup mirror » exécutant chaque nuit :

```powershell
docker cp bovo-backup:/backups \\NAS-BOVO\Sauvegardes\bovo\
```

### Approche native

Créer une tâche planifiée qui exécute quotidiennement :

```powershell
& "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" -U bovo bovo `
  | Compress-Archive -DestinationPath "D:\Backups\bovo-$(Get-Date -f 'yyyy-MM-dd').zip"
```

### Mises à jour applicatives

Docker :

```powershell
cd C:\Bovo\server
git pull
cd bovo-server
docker compose up -d --build
```

Natif :

```powershell
cd C:\Bovo\server
git pull
cd bovo-server
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
nssm restart BovoASFManager
```

---

## Migration ultérieure vers un VPS

Objectif : aucune modification de code. La procédure ci-dessous est valable
**quelle que soit l'approche choisie** (Docker ou natif sur Windows).

### Sur le PC Windows (source)

Docker :

```powershell
docker exec bovo-db pg_dump -U bovo bovo > C:\Bovo\dump.sql
docker cp bovo-api:/data/documents C:\Bovo\documents-backup
```

Natif :

```powershell
& "C:\Program Files\PostgreSQL\16\bin\pg_dump.exe" -U bovo bovo > C:\Bovo\dump.sql
# Rien à copier pour les documents si vous ne les avez pas encore activés
```

### Sur le VPS (cible)

```bash
# 1. Cloner le même dépôt
git clone https://github.com/nfestryer-hub/BOVO-ASF-PDF-READER.git
cd BOVO-ASF-PDF-READER/bovo-server

# 2. Copier le .env personnalisé (SCP depuis le PC)
scp bovo-serveur-windows:C:/Bovo/server/bovo-server/.env .env

# 3. Démarrer la pile
docker compose up -d --build

# 4. Restaurer la base
scp bovo-serveur-windows:C:/Bovo/dump.sql .
docker compose exec -T db psql -U bovo -d bovo < dump.sql

# 5. Restaurer les documents
scp -r bovo-serveur-windows:C:/Bovo/documents-backup ./documents
docker cp ./documents bovo-api:/data/
```

### Sur les clients desktop

Mettre à jour l'URL du serveur dans les Paramètres de l'application
Bovo ASF Manager :

```
Ancienne : http://192.168.1.42:8000
Nouvelle : https://bovo.votredomaine.fr
```

**Aucun code modifié.** La compatibilité est garantie car :

- Le serveur consomme les mêmes variables d'environnement
- La base de données est standard PostgreSQL 16
- Les documents sont des fichiers dans un volume Docker
- Le client desktop utilise `REACT_APP_BACKEND_URL`-style env var
  (variable `BOVO_API_URL` côté client — voir écran Paramètres)

### Basculement à froid recommandé (5 min de coupure)

1. Prévenir les utilisateurs (message Teams / mail).
2. Arrêter le serveur Windows : `docker compose stop`.
3. Faire un dump final + copier documents.
4. Restaurer sur VPS (étapes ci-dessus).
5. Publier la nouvelle URL dans les clients.
6. Vérifier `/api/health` et connexion utilisateur.
7. Arrêt définitif du serveur Windows.

---

## Support

En cas de problème :

- Logs Docker : `docker compose logs api` / `docker compose logs db`
- Logs natif : Event Viewer Windows → « Windows Logs » → Application ;
  ou `Get-EventLog -LogName Application -Source BovoASFManager -Newest 50`
- Health : `curl http://localhost:8000/api/health` doit retourner
  `{"status":"ok","version":"1.0.0"}`
