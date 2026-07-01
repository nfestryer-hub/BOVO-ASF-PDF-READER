# BOVO Planning Manager — PRD

## Problème / Objectif
Logiciel desktop professionnel (Python 3.12+, CustomTkinter, SQLite3, PyMuPDF)
de gestion automatique des interventions ASF de BOVO & FILS. L'utilisateur
sélectionne des PDF de listing d'ouvrages ; le logiciel extrait les données,
crée/met à jour les interventions en SQLite, et met à jour planning + calendrier.
Développé par HENRI Dylan.

## Stack & emplacement
- Projet desktop autonome dans `/app/bovo/` (indépendant du scaffold web).
- Python 3.12+, CustomTkinter, SQLite3, PyMuPDF (fitz), openpyxl, Pillow.
- Lancement local : `python main.py`.

## Architecture (livrée V1)
main.py · app/{gui,database,models,parser_pdf,planner,calendar,exporter,
inspections,logger,settings,utils}.py · database/bovo.db · assets/logo.png · tests/.
GUI sans logique métier ; logique répartie dans les modules.

## Implémenté
### V1 (2026-06-30)
- Splash animé (logo BOVO + « Développé par HENRI Dylan »), fondu in/out.
- Accueil « Bonjour {utilisateur} » + dashboard (total, PDF, terminées, à faire,
  autoroutes, secteurs, dernière MAJ, état base).
- Parser PDF tabulaire (PyMuPDF find_tables) calibré sur le vrai listing :
  51 interventions / 5 autoroutes extraites. Mapping colonnes Objet, Identifiant
  (=ouvrage), Autoroute, PR, Sens, Longueur, Diamètre, Type, Planification.
- DateParser : 15/06/2026, 15 et 16/07/2026, 23 au 26/11/2026,
  27-28-29-30/07/2026, 29-30/06/2026, « nuits 22 et 23/06/2026 ».
- SQLite : tables interventions, pdf_files, logs, settings ; dédoublonnage par
  ouvrage (upsert) ; statistiques ; recherche multi-critères ; thread-safe.
- Planner : import 1 PDF / N PDF / dossier, progression (thread + queue).
- Calendrier mensuel interactif (couleurs par statut, compteur/jour, fiche
  détaillée + bouton « Ouvrir le PDF »).
- Recherche instantanée + filtres ; exports Excel/CSV/JSON/PDF.
- Journal des actions ; paramètres (thème, autosave, dossiers).
- Qualité : Ruff/Flake8/MyPy 0 erreur ; 12 tests pytest OK ; smoke GUI sous
  Xvfb OK (toutes vues rendues).

### Module Inspections ASF (2026-06-30 — itération 2)
- Nouveau module `app/inspections.py` (service) + tables dynamiques génériques.
- 4 modules éditables (CRUD + listes déroulantes du Référentiel) : Inspections,
  Rapports d'inspection, Incidents, Matériel.
- Import du classeur Excel ASF (8 inspections / 8 rapports / 2 incidents /
  8 matériels + Référentiel).
- Complétion AUTO : un rapport (Identifiant) marque l'intervention liée
  « Terminée » → vert dans le calendrier.
- KPIs ASF au dashboard (ML inspectés 2518, regards 56, heures 38.2, ML/h 65.8).
- 15 tests pytest OK ; Ruff/MyPy/Flake8 0 erreur ; smoke GUI Xvfb OK.

### Itération 3 — Ergonomie Inspections & exports (2026-07-01)
- Auto-calcul **ML Inspectés** dans le formulaire Inspection dès que
  PK Départ & PK Arrivée sont saisis (formats `12+345`, `12.345`, `12,345`,
  `12`, `12345`, préfixes `PR/PK`).
- Auto-calcul **Heures Totales** dès que Heure Début & Heure Fin sont saisies
  (`HH:MM`, `HHhMM`, `8h`, `8,5`) — gère le passage à minuit (22:00→02:00 = 4 h).
- **Pré-remplissage du Rapport d'inspection** depuis la dernière inspection
  ajoutée : date, N° Inspection, autoroute, secteur, inspecteur (=opérateur),
  prestataire = « BOVO & FILS ». Photo/Description/Identifiant/etc. laissés
  vides (à saisir).
- **Export PDF tableur** (paysage A4) pour chaque module ASF via un bouton
  « 📄 Export PDF » dans la barre d'outils (Inspections, Rapports, Incidents,
  Matériel).
- **Icône de fenêtre** BOVO appliquée (barre de tâches Windows/Linux/macOS).
- 31 tests pytest OK (16 nouveaux) ; Ruff 0 erreur ; smoke GUI Xvfb OK.

### Itération 5 — Bovo ASF Manager v1.1 : renommage + fixes UX + Backend serveur (2026-07-01)

**Phase A — UX (client desktop)**
- Renommage global : « BOVO Planning Manager » → **Bovo ASF Manager** (v1.1.0)
- Suppression de l'onglet Carte (les utilisateurs disposent déjà d'un logiciel GPS)
- Sidebar refondue : `CTkScrollableFrame` pour la nav + bloc bas fixe (user + « ⎋ Se déconnecter » + version) → le bouton reste visible même chez l'Admin
- Export PDF tableur en **A3 paysage** avec largeurs proportionnelles au contenu + wrapping automatique via `insert_textbox` (lisibilité maximale)
- **« Se souvenir de moi »** au login : stocke `remembered_username` + `remembered_hash` (bcrypt) dans `settings`. Auto-login silencieux au prochain lancement (via `AuthService.try_auto_login`), avec purge automatique si le mot de passe a changé.

**Phase B — Backend serveur multi-utilisateurs (`/app/bovo-server/`)**
- **FastAPI** (Python 3.12) + **PostgreSQL 16** + **JWT** (PyJWT, HS256, access 8h + refresh 30j)
- **Auth** : bcrypt (coût 12), seed idempotent Admin, brute force lock (5 échecs / 15 min via table `login_attempts`)
- **RBAC** : dépendances `require_admin` / `require_editor` (Admin/Planificateur/Consultant)
- **Endpoints REST** : `/api/auth/*`, `/api/users`, `/api/interventions`, `/api/modules/{sheet}` (inspections/rapports/incidents/materiel avec colonne JSONB), `/api/documents` (multipart + download), `/api/audit`, `/api/health`, `/api/events` (SSE)
- **Synchronisation temps-réel via SSE** : `EventBroadcaster` avec `bind_loop` capturant la loop principale, `publish_sync` utilisant `run_coroutine_threadsafe` (compatible endpoints synchrones), keep-alive 20 s, subscribe / unsubscribe thread-safe
- **Audit trail** : chaque écriture métier enregistre `username`, `role`, `action`, `entity`, `entity_id`, `before`, `after` (JSONB)
- **docker-compose** : services `db` (Postgres) + `api` (Uvicorn) + `backup` (pg_dump quotidien, gzip, rétention 14 jours) + volumes persistants (`db-data`, `documents`, `backups`)
- **Dockerfile** slim Python 3.12 + healthcheck curl
- **Migration SQLite → PostgreSQL** : script `migrate_sqlite_to_postgres.py` idempotent (users / interventions / modules / documents / settings / audit)
- **Documentation** : README complet avec setup VPS + nginx reverse-proxy (SSE-friendly) + rotation backups + restauration

**Phase B — Client desktop : socle réseau**
- `app/api_client.py` : `ApiClient` avec `requests.Session`, refresh 401 automatique, `Tokens`, `ApiError`, endpoints (auth/users/interventions/modules/documents/audit)
- `app/sync.py` : `SseListener` (thread daemon, reconnexion exponentielle 2s → 60s, JSON parse, callback thread-safe)
- Test E2E : client Python parle à API → login OK, création intervention → événement SSE reçu instantanément, refresh token OK, upload/download OK

**Tests & qualité**
- **41 tests pytest OK** (client desktop, Phase A + auto-login)
- Backend testé via curl (health, login, brute force, RBAC 403, SSE stream, refresh, upload) + test E2E Python (SSE + REST)
- **Ruff 0 erreur** sur client + serveur

### Comptes seedés (serveur)
- Admin : `Bovo` / `ibak23` (créé automatiquement au démarrage via `ADMIN_PASSWORD`)
- Autres comptes : à créer via l'écran « Utilisateurs » ou `POST /api/users`

### Backlog restant (P0)
- Refactor complet du client desktop pour parler à l'API à la place de la SQLite (services `Planner` / `InspectionService` / `AuthService` locaux → services distants basés sur `ApiClient`)
- Écran de configuration serveur (URL + test de connexion) au premier lancement
- Bouton « Synchroniser maintenant » (refresh manuel) + indicateur d'état SSE dans la sidebar
- PyInstaller `.exe` Windows avec URL du serveur bakée

### Backlog résiduel (P1/P2)
- Glisser-déposer PDF · impression plannings · sauvegardes auto programmées côté client · notifications toast temps-réel sur événements SSE

## Personas
- Planificateur BOVO : importe les listings, suit le planning, exporte.

## Backlog (architecture évolutive prévue)
- P1 : glisser-déposer de PDF ; impression des plannings ; sauvegardes auto
  programmées ; notifications.
- P2 : multi-utilisateurs + rôles ; historique des modifications ;
  synchronisation réseau ; carte interactive ; gestion documentaire ;
  mises à jour logicielles ; tableau de bord avancé.

## Notes
- Pas d'authentification (mono-poste). Aucun credential.
- Colonne « secteur » absente du PDF source → champ vide (extensible).
