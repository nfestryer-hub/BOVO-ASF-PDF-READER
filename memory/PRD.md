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

## What's been implemented (Jan 2026 — V4 + ASF layout)

### Correctifs V4 (session 1)
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
- **Fix 3** (Se souvenir de moi) : le refresh token JWT est dupliqué
  dans le JSON utilisateur, ce qui protège contre une perte de la base
  SQLite locale.
- **Fix 4** (`bovo-backup`) : remplacement du `command` folded scalar
  YAML par un script shell dédié `bovo-server/scripts/backup.sh` monté
  en volume, avec rotation atomique.

### Mise en page ASF (session 2 — actuelle)
- **Formulaire Rapport d'inspection en 4 sections ASF** avec **5 layouts
  distincts** (un par onglet du classeur Excel ASF) :
  - **Caniveau / Fossé** : Caractéristiques = Type mat + Emplacement + Si obj à req ; Surveillance = État + Comm + Photo
  - **Cunette** : Caractéristiques = Type mat + Emplacement ; Surveillance = Si obj à req + État + Comm + Photo
  - **Collecteur enterré / Descente d'eau** : Caractéristiques = Si obj à req (seul) ; Surveillance = État + Comm + Photo
  - Le formulaire propose un sélecteur « Type d'ouvrage » qui **rebuild dynamiquement** les 4 cartes colorées selon le type choisi
  - Nouveau champ DB `commentaire` (long text) pour la section « Informations Générales »
  - Migration SQLite auto (`ALTER TABLE ADD COLUMN`) pour compat avec anciennes bases
- **Export PDF ASF multi-ouvrages** : une grille distincte par type
  d'ouvrage ASF dans le PDF final (A3 paysage). Chaque groupe a son
  bandeau titre + ses 4 en-têtes de sections spécifiques.
- **Référentiels ASF** : tous à jour (type, type_materiau, emplacement,
  requalif, etat_cunettes).
- **Vue Inspections modernisée** : bandeau KPIs (4 cartes colorées),
  badges colorés Statut/Urgence/État, état vide illustré.
- **Login enrichi** : message d'aide sous "Se souvenir de moi".
- **Paramètres refactoré** : 3 cartes + bouton « Reconfigurer le serveur ».

### Revue post-import + statut « À planifier » (session 3 — actuelle)
- **Nouveau statut `A_PLANIFIER` = « À planifier »** (couleur gris `#9AA0A6`)
  ajouté à :class:`StatutIntervention`. Il représente un **brouillon**
  d'intervention importée depuis un PDF, avant validation manuelle.
- **Import PDF → statut par défaut « À planifier »** (au lieu de
  « Planifiée » avant). Les interventions apparaissent immédiatement
  dans le calendrier en gris (couleur distinctive) mais ne sont pas
  considérées comme confirmées.
- **Nouveau dialogue `ImportReviewDialog`** ouvert automatiquement après
  chaque import PDF :
  - Liste toutes les interventions créées/mises à jour avec case à cocher.
  - Boutons « Tout cocher » / « Tout décocher ».
  - Compteur temps-réel « N/N cochés → passeront en Planifiée ».
  - « Confirmer la planification » → promeut les lignes cochées en
    `PLANIFIEE`. Les non cochées restent en `A_PLANIFIER`.
  - « Fermer sans confirmer » → tout reste en brouillon.
- **Reprogrammation intelligente** : si un ouvrage réapparaît dans un
  nouveau PDF avec une date future, l'entrée en base est mise à jour
  (via `upsert_intervention` sur clé `ouvrage`) — pas de doublon.
- **Préservation des statuts avancés** : un ouvrage déjà en
  `EN_COURS` ou `TERMINEE` n'est PAS écrasé lors d'un ré-import.
  Un ouvrage `PLANIFIEE` avec nouvelle date future reste `PLANIFIEE`
  (juste la date change).

## Tests
- `tests/test_bovo.py` : 41 tests (parser, DB, planner, calendrier, auth…).
- `tests/test_remember_me.py` : 6 tests.
- `tests/test_v4_fixes.py` : 5 tests.
- `tests/test_asf_export.py` : 4 tests (PDF ASF + multi-ouvrages).
- `tests/test_import_review.py` (**nouveau**) : 5 tests (statut par défaut,
  imported_ids, reprogrammation, préservation En cours).
- **Total : 61 tests, 100 % passing.**

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
