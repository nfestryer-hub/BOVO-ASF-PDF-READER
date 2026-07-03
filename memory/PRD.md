# Bovo ASF Manager — PRD

## Problem statement (V4, Jan 2026)
Application desktop CustomTkinter + backend FastAPI/PostgreSQL pour gérer
les interventions ASF réalisées par BOVO. La branche V4 corrige 4 bugs
critiques signalés par le client :

1. **Import PDF cassé** : le journal affichait « Démarrage : 1 fichier(s) »
   puis rien n'était créé dans le calendrier ni les interventions.
2. **Dialogue de config serveur affiché à chaque démarrage** : devait
   n'apparaître qu'au tout premier lancement.
3. **« Se souvenir de moi »** : la reconnexion silencieuse échouait.
4. **`bovo-backup` (Postgres)** : le service ne démarrait pas
   (`/bin/sh: syntax error: unexpected "|"`).

L'application doit aussi être visuellement plus soignée.

## Architecture
- **`/app/bovo/`** — client desktop CustomTkinter (Python 3.11+).
  - `app/parser_pdf.py` : extraction tabulaire PyMuPDF.
  - `app/remote_services.py` : adaptateurs REST (`RemoteAuthService`,
    `RemotePlanner`, `RemoteInspectionService`, `RemoteDocumentService`).
  - `app/api_client.py` : client HTTP + JWT refresh automatique.
  - `app/settings.py` : préférences SQLite locales + miroir JSON utilisateur.
  - `app/local_config.py` (**nouveau**) : stockage JSON durable dans
    `%APPDATA%/BovoASF` (Windows) ou `~/.config/BovoASF` (Linux/macOS).
  - `app/gui.py` : interface CustomTkinter (accueil, calendrier,
    interventions, inspections, documents, journal, paramètres).
- **`/app/bovo-server/`** — backend FastAPI + PostgreSQL 16 + docker-compose.
  - Services : `db`, `api`, `backup`.
  - `scripts/backup.sh` (**nouveau**) : script shell dédié pour le
    conteneur de sauvegarde.

## User personas
- **Admin (Bovo)** : peut tout faire, y compris gérer les utilisateurs.
- **Planificateur (Dylan HENRI)** : planifie les interventions,
  importe les PDF, gère les modules ASF.
- **Consultant (ASF)** : consultation seule des inspections/documents.

## Core requirements (stables)
- Authentification REST JWT (access 8h + refresh 30j).
- Import PDF (parsing tabulaire + extraction de dates FR).
- Calendrier mensuel visuel avec statuts colorés.
- Modules ASF éditables (inspections, rapports, incidents, matériel).
- Export multi-format (Excel, CSV, JSON, PDF).
- Documents attachés aux entités.
- Journal d'activité local + audit trail serveur.

## What's been implemented (Jan 2026 — V4)
- **Fix 1** (import PDF) : correction de l'import cassé
  `from app.pdf_parser` → `from app.parser_pdf` dans `remote_services.py`.
- **Fix 2** (config serveur persistante) :
  - Nouveau module `app/local_config.py` qui écrit
    `%APPDATA%/BovoASF/bovo_config.json`.
  - `Settings` synchronise automatiquement `server_url`,
    `remembered_username`, `remembered_refresh_token` entre SQLite et JSON.
  - Le dialogue ne s'affiche plus au démarrage tant que l'URL est
    connue (via SQLite OU JSON).
  - Bouton « 🔧 Reconfigurer le serveur » ajouté dans Paramètres.
- **Fix 3** (Se souvenir de moi) :
  - Le refresh token JWT est désormais dupliqué dans le JSON utilisateur,
    ce qui protège contre une perte de la base SQLite locale.
  - Message informatif ajouté sous la case « Se souvenir de moi » :
    « Votre session sera reconduite automatiquement pendant 30 jours. »
- **Fix 4** (`bovo-backup`) :
  - Remplacement du `command` folded scalar YAML fragile par un script
    shell séparé `bovo-server/scripts/backup.sh` monté en volume.
  - Ajout de variables d'environnement configurables
    (`BACKUP_KEEP_COUNT`, `BACKUP_INTERVAL_SECONDS`).
  - Logs plus lisibles + rotation atomique (`.tmp` → renommage).
- **Bonus UX** :
  - Vue Paramètres refactorée en 3 cartes (Apparence, Serveur,
    Emplacements) avec `CTkScrollableFrame`.
  - Affichage de l'URL courante du serveur.
  - Fenêtre de connexion agrandie (640 px) pour le message d'aide.
  - Journal d'import PDF affiche maintenant explicitement le nombre
    d'interventions détectées par fichier + les erreurs par ouvrage.

## Tests
- `tests/test_bovo.py` : 41 tests (parser, DB, planner, calendrier, auth…).
- `tests/test_remember_me.py` : 6 tests (persistance token, auto-login).
- `tests/test_v4_fixes.py` (**nouveau**) : 5 tests (import PDF, JSON mirror,
  restauration après effacement DB).
- **Total : 52 tests, 100 % passing.**

## Backlog / P1
- Test end-to-end desktop → backend (nécessite un environnement Windows
  ou une VM CustomTkinter).
- Endpoint `/api/backup/status` pour surfacer l'état des sauvegardes
  dans l'admin GUI.
- Sync SSE en cas de reconnexion réseau (currently best-effort).

## P2 / futures évolutions
- Support multi-tenant (plusieurs entreprises sur le même backend).
- Statistiques ML/h automatiques par autoroute (radar).
- Export ZIP complet (PDF + Excel + documents) d'une intervention.
