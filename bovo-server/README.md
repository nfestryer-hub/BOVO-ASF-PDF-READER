# Bovo ASF Manager Server

API REST centralisée du logiciel **Bovo ASF Manager**. Toutes les données
(interventions, inspections ASF, rapports, documents, journal d'audit,
utilisateurs) sont stockées dans PostgreSQL. Les clients desktop
CustomTkinter parlent uniquement à cette API — **plus jamais directement à
la base de données**.

## Architecture

```
┌──────────────────┐     HTTPS/REST     ┌──────────────────┐
│  Client desktop  │ ─────────────────▶ │  FastAPI (API)   │
│  (CustomTkinter) │ ◀───── SSE ─────── │   [uvicorn]      │
└──────────────────┘                    └──────────┬───────┘
                                                    │
                                          PostgreSQL 16 (bovo)
                                          + backups quotidiens
```

- **FastAPI** (Python 3.12) : REST + Server-Sent Events
- **PostgreSQL 16** : base de données centralisée
- **JWT** : authentification stateless (Bearer tokens)
- **bcrypt** (coût 12) : hachage des mots de passe
- **docker-compose** : orchestration API + base + sauvegardes

> 💡 **Pour un déploiement sur un PC Windows interne (poste BOVO qui reste
> allumé)** : consultez le guide dédié [DEPLOY_WINDOWS.md](DEPLOY_WINDOWS.md)
> et les scripts PowerShell d'installation automatique dans le dossier
> [`windows/`](windows/). L'app est portable : les mêmes fichiers
> fonctionneront ensuite tels quels sur un VPS Linux (script de migration
> `migrate-to-vps.ps1` fourni).

## Déploiement sur un VPS

Prérequis :

- Docker et docker-compose installés (`curl -fsSL https://get.docker.com | sh`)
- Ports 8000 (ou 443 derrière un reverse proxy) ouverts
- Nom de domaine + certificat TLS *(recommandé mais optionnel)*

Étapes :

```bash
# 1. Copier le dépôt sur le VPS
scp -r bovo-server/ user@votre-vps:/opt/bovo/

# 2. Se connecter et préparer la configuration
ssh user@votre-vps
cd /opt/bovo/bovo-server

# 3. Générer un secret fort et éditer .env
cp .env.example .env
sed -i "s|remplacez-par-openssl-rand-hex-32|$(openssl rand -hex 32)|" .env
nano .env   # personnaliser POSTGRES_PASSWORD et ADMIN_PASSWORD

# 4. Démarrer la pile
docker compose up -d --build

# 5. Vérifier
curl -fsS http://localhost:8000/api/health
docker compose logs -f api
```

Le compte Admin par défaut est créé automatiquement (`ADMIN_USERNAME` /
`ADMIN_PASSWORD` du `.env`). Les autres utilisateurs se créent via l'API
(endpoint `POST /api/users`) ou l'écran « Utilisateurs » du client.

### Reverse proxy (recommandé, TLS)

Exemple minimal avec **nginx** :

```nginx
server {
    listen 443 ssl http2;
    server_name bovo.votredomaine.fr;

    ssl_certificate     /etc/letsencrypt/live/bovo.votredomaine.fr/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bovo.votredomaine.fr/privkey.pem;

    # SSE : désactiver le buffering.
    location /api/events {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_read_timeout 24h;
        proxy_send_timeout 24h;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 200m;
    }
}
```

## Endpoints

| Méthode | Chemin                                | Rôles requis        |
| :------ | :------------------------------------ | :------------------ |
| GET     | `/api/health`                         | Public              |
| POST    | `/api/auth/login`                     | Public              |
| POST    | `/api/auth/refresh`                   | Public (refresh JWT)|
| GET     | `/api/auth/me`                        | Authentifié        |
| GET     | `/api/auth/config`                    | Public              |
| GET     | `/api/users`                          | Admin               |
| POST    | `/api/users`                          | Admin               |
| PATCH   | `/api/users/{id}`                     | Admin               |
| DELETE  | `/api/users/{id}`                     | Admin               |
| POST    | `/api/users/{id}/password`            | Admin ou soi-même   |
| GET     | `/api/interventions`                  | Authentifié        |
| POST    | `/api/interventions`                  | Admin / Planificateur |
| GET     | `/api/interventions/{id}`             | Authentifié        |
| PATCH   | `/api/interventions/{id}`             | Admin / Planificateur |
| DELETE  | `/api/interventions/{id}`             | Admin / Planificateur |
| GET     | `/api/modules/{sheet}`                | Authentifié        |
| POST    | `/api/modules/{sheet}`                | Admin / Planificateur |
| PATCH   | `/api/modules/{sheet}/{id}`           | Admin / Planificateur |
| DELETE  | `/api/modules/{sheet}/{id}`           | Admin / Planificateur |
| GET     | `/api/documents`                      | Authentifié        |
| POST    | `/api/documents` (multipart)          | Admin / Planificateur |
| GET     | `/api/documents/{id}/download`        | Authentifié        |
| DELETE  | `/api/documents/{id}`                 | Admin / Planificateur |
| GET     | `/api/audit`                          | Admin / Planificateur |
| GET     | `/api/events?token=…`                 | Authentifié (SSE)  |

Sheets acceptés pour `/api/modules/{sheet}` : `inspections`, `rapports`,
`incidents`, `materiel`.

Documentation Swagger interactive : `https://votre-domaine/docs`.

## Sauvegardes

Le service `backup` (docker-compose) exécute chaque jour un `pg_dump` gzip
dans le volume `backups`. Les **14 dernières** archives sont conservées.

Pour restaurer une sauvegarde :

```bash
docker compose exec -T db psql -U bovo -d bovo < /chemin/vers/bovo-2026-06-30.sql
```

Pour copier localement le dossier des sauvegardes :

```bash
docker cp bovo-backup:/backups ./backups-locales
```

## Sécurité

- Mots de passe stockés en **bcrypt** (jamais en clair).
- Tokens JWT signés (HS256) avec un secret fort — **régénérez `JWT_SECRET`
  en production** (via `openssl rand -hex 32`).
- Le refresh token dure 30 jours par défaut ; l'access token 8 h. Réduisez
  ces valeurs pour des postes en lecture seule (`ACCESS_TOKEN_MINUTES`).
- Protection anti-brute-force : 5 échecs consécutifs sur 15 minutes
  déclenchent un blocage.
- Toutes les modifications sont journalisées dans `audit_log` (qui/quoi/quand).

## Développement local

```bash
# Sans Docker (pour développer)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_DSN=postgresql+psycopg://bovo:bovo@localhost:5432/bovo
export JWT_SECRET=$(openssl rand -hex 32)
export ADMIN_PASSWORD=ibak23
uvicorn app.main:app --reload --port 8000
```
