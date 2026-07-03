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
- **Formulaire Rapport d'inspection en 4 sections ASF** : refonte
  complète du `RowFormDialog` pour ``sheet == "rapports"``. Affichage
  horizontal en 4 cartes colorées (rouge / bleu / orange / vert)
  reprenant exactement la structure du classeur ASF « Form visites
  assainissement V2026-06-01 » :
  1. Informations Générales (Identifiant, Date de visite, Prestataire, Inspecteur, N° Inspection, Autoroute, Secteur, Sens)
  2. Caractéristiques de l'ouvrage (Type d'ouvrage, Type de matériau, Emplacement, Latitude, Longitude, Lien Maps)
  3. Surveillance générale (Si objet à requalifier, État général de l'ouvrage, Type de défaut, Urgence, Statut)
  4. Autres documents rattachés à la visite (Commentaires, Photo(s))
- **Export PDF ASF** : nouvelle méthode
  ``Exporter.asf_rapports_to_pdf`` qui produit un PDF A3 paysage avec
  les 4 en-têtes de sections fusionnés + sous-en-têtes de colonnes,
  matchant visuellement le classeur Excel ASF. Utilisée
  automatiquement pour l'export du module « Rapports d'inspection ».
- **Référentiels ASF** : mise à jour de `type` (Caniveau, Collecteur
  enterré, Cunette, Fossé, Descente d'eau), `type_materiau` (matériaux
  ASF réels), `emplacement` (nouveau — Haut/Bas de talus, GBA…),
  `requalif` (5 flags ASF), `etat_cunettes` (5 niveaux ASF).
- **Vue Inspections modernisée** : bandeau KPIs (4 cartes colorées
  affichant le nombre par module), sous-titre "conforme au formulaire
  ASF V2026-06-01", badges colorés pour Statut / Urgence / État
  général (vert/orange/rouge), état vide illustré.
- **Vue Paramètres refactorée** : 3 cartes (Apparence, Connexion
  serveur, Emplacements), avec bouton « Reconfigurer le serveur ».
- **Login enrichi** : message d'aide sous "Se souvenir de moi" :
  « Votre session sera reconduite automatiquement pendant 30 jours ».

## Tests
- `tests/test_bovo.py` : 41 tests (parser, DB, planner, calendrier, auth…).
- `tests/test_remember_me.py` : 6 tests (persistance token, auto-login).
- `tests/test_v4_fixes.py` : 5 tests (import PDF, JSON mirror, wipe DB).
- `tests/test_asf_export.py` (**nouveau**) : 3 tests (PDF ASF avec
  sections, service export routing, format A3 paysage).
- **Total : 55 tests, 100 % passing.**

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
