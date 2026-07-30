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
### V1.7.1 (2026-07-30) — MSI cx_Freeze 8.6.4 + auto-update HTTP/SHA256 ✅
- **setup_msi.py** refait pour cx_Freeze **8.6.4** + Python **3.13.14** :
  * Deux `Executable()` (ProgramMenuFolder + DesktopFolder) → raccourcis
    Bureau + menu Démarrer via l'API officielle 8.x.
  * `upgrade_code = "{7B9F1E4E-3F16-4E2D-9A8F-1B4C6E2D9A3F}"` (fixe, ne
    jamais changer) → Windows Installer remplace proprement l'ancienne
    version.
  * `all_users=True` → install per-machine (nécessite admin).
  * `initial_target_dir=[ProgramFiles64Folder]\Bovo`.
  * `target_name=Bovo-<version>-win64` → `dist/Bovo-1.7.0-win64.msi`.
- **build-msi.ps1** : pin `cx_Freeze==8.6.4`, SHA256 auto post-build.
- **publish-release.ps1** : accepte `-MsiUrl` HTTP en plus de `-Share` UNC.
  Génère `latest.json` avec **version + msi_url + msi_path + sha256 +
  size + release_notes + mandatory + published_at**.
- **`app/updater.py`** enrichi :
  * `UpdateInfo` avec msi_url + msi_path + sha256 + size.
  * `_sha256_file` (streaming), `_download_msi` (téléchargement HTTP en
    `.part` atomique + vérif SHA256), `install_update` (HTTP prioritaire
    avec fallback UNC, `msiexec /i /qn /norestart /L*v`).
  * Installation totalement silencieuse par défaut (`/qn`), on peut
    passer à `/qb` (barre de progression) via `silent=False`.
- **Préservation `%APPDATA%\Bovo`** : le MSI installe dans `Program
  Files\Bovo\`. Windows Installer via upgrade_code désinstalle+réinstalle
  le Program Files SANS jamais toucher au dossier utilisateur.
- **Tests** : testing agent iter #6 : **63/63 pytest** ✅ (5 nouveaux tests
  SHA256/download) + smoke_updater_e2e ✅ + smoke_test_gui ✅ +
  repro_remember_gui ✅ + smoke_multiselect ✅.

### V1.7 (2026-07-30) — Multi-sélection & suppression groupée ✅
- **Vue Interventions** : checkbox par ligne + case « Tout sélectionner » +
  bouton « Supprimer sélection (N) » (compteur dynamique).
- **Vue Inspections ASF** (4 feuilles inspections/rapports/incidents/
  materiel) : même dispositif, suppression via `RemoteInspectionService.delete_row`.
- **Nettoyage auto** : IDs devenus invisibles (filtre/recherche) retirés
  de la sélection automatiquement.
- **Permission-aware** : checkboxes + bouton visibles UNIQUEMENT pour les
  rôles Admin/Planificateur ; Consultant reste read-only.
- **Confirmation** avant suppression + toast récap (« N supprimé(s), M échec(s) »).
- **Tests** : testing agent iter #5 : 58/58 pytest ✅ + smoke_multiselect ✅
  + smoke_test_gui ✅ + repro_remember_gui ✅.

### V1.6 (2026-07-30) — Colonne ID Ouvrage visible + Packaging MSI + Auto-updates ✅
- **Vue Inspections ASF** : colonne `id_ouvrage` mise en valeur (largeur
  95 px dédiée, label header en accent rouge, valeur en gras+accent).
  Nouveau dict `_COL_WIDTHS` avec largeurs personnalisées par colonne
  (id ~95, dates ~100, observations ~260) pour une meilleure hiérarchie
  visuelle. Le scroll horizontal introduit précédemment permet de
  visualiser toutes les colonnes.
- **Packaging MSI** (cx_Freeze) :
  * `setup_msi.py` avec `upgrade_code` GUID fixe → chaque nouvelle
    version remplace proprement l'ancienne (via Windows Installer).
  * Installation à `C:\Program Files\Bovo\`, raccourcis menu Démarrer
    + bureau, entrée « Ajouter/Supprimer programmes ».
  * `build-msi.ps1` (build) et `publish-release.ps1` (publication).
- **Auto-update** :
  * `app/updater.py` : `UpdateInfo`, `check_for_update`, `_parse_version`
    (SemVer tolérant), `check_for_update_async` (thread daemon jamais
    bloquant), `launch_installer` (msiexec /i avec DETACHED_PROCESS).
  * `Settings.update_source` : chemin UNC ou URL vers `latest.json`.
  * `BovoApp._schedule_update_check` appelé au démarrage → bandeau non
    bloquant si MAJ dispo (ou modal si `mandatory=true`).
  * Vue Paramètres : champ « Source des mises à jour » + bouton
    « Vérifier » + affichage de la version installée.
- **Tests** : testing agent iter #4 : **58/58 pytest** ✅ (11 nouveaux
  test_updater.py) + smoke_test_gui ✅ + repro_remember_gui ✅.

### V1.5.1 (2026-07-29) — Persistance frozen mode
- `utils.py` détecte `sys.frozen` → données utilisateur dans
  `%APPDATA%\Bovo\` (persistant per-user), assets bundle via
  `sys._MEIPASS`. Nécessaire pour que « Se souvenir de moi » etc.
  survivent quand l'exe tourne depuis un partage réseau.

### V1.6.0 (2026-07-29) — Bug fix Excel & scroll horizontal ✅
- **Bug #1 : décalage colonnes Excel** — l'utilisateur a ajouté une colonne
  `ID` en position 4 dans la feuille Inspections. Corrections :
  * Ajout de `id_ouvrage` dans `ORDERED_COLUMNS['inspections']` (pos 3) et
    `FORM_FIELDS['inspections']` (label "ID Ouvrage").
  * `_import_sheet` refactoré en **header-based** avec normalisation
    accents/espaces/casse + table d'aliases `_EXCEL_LABEL_ALIASES`
    (`"ID" → id_ouvrage`). Robuste aux évolutions futures du classeur
    (colonnes ajoutées, ré-ordonnées, retitrages).
  * Rétro-compat validée : l'ancien classeur (17 cols) et le nouveau
    (18 cols avec ID) importent tous les deux correctement.
- **Bug #2 : pas de scrollbar horizontale** dans le tableau des modules
  ASF (Rapports = 21 colonnes). Corrections :
  * `_build_module_tab` remplace `CTkScrollableFrame` par
    `tkinter.Canvas` + `CTkScrollbar` horizontal & vertical.
  * Molette : verticale par défaut, **Shift+molette** pour horizontal.
  * Scroll region recalculé automatiquement à chaque changement d'inner.
  * Canvas est un widget tk pur → couleur passée en string (résolution
    du tuple light/dark de CTk selon `get_appearance_mode()`).
- **Tests** : testing agent iter #3 : 47/47 pytest ✅ + smoke_test_gui ✅
  + repro_remember_gui ✅ + import nouveau Excel: id_ouvrage='21764' ✅.

### V1.5 (2026-07-01) — Migration REST complète du GUI ✅
- **BovoApp** accepte désormais `client=` et instancie `RemotePlanner` /
  `RemoteInspectionService` / `RemoteDocumentService` à la place des services
  SQLite locaux. La DB locale ne sert plus qu'aux paramètres, journal
  local et cache offline.
- **Backend** : renommage `observations→commentaire` + ajout `longueur`,
  `diametre` sur `Intervention` (models.py + schemas.py). Nécessite un
  drop/create DB (pas de migrations Alembic).
- **RemotePlanner** aligné exactement sur `Planner` (compat GUI) :
  * `get_statistics()` → `{total, terminees, a_faire, pdfs, autoroutes,
    secteurs, derniere_maj, db_ok}` (plus `avec_pdf`).
  * `filter_options()` → `{autoroutes, secteurs, statuts}` (plus de
    préfixes `Toutes/Tous`).
  * `build_calendar(year, month)` utilise `CalendarModel.build_month`.
  * `list_between(start, end)` accepte str ISO ou `date`.
  * `search(...)` accepte `search/statut/autoroute/secteur/ouvrage/query`.
  * `upsert()` sérialise `commentaire`, `longueur`, `diametre`.
  * `import_pdfs()` renvoie un `ImportResult` mirror (files_processed,
    interventions_created, interventions_updated, errors: list[str]).
- **RemoteInspectionService** : ajout `referentiel(ref_key)` (cache local
  depuis `DEFAULT_REFERENTIEL`) ; `kpis()` renvoie `nb_inspections` + `ml_h`.
- **RemoteDocumentService** utilisé pour download/upload ; ouverture native
  passe désormais par un cache temp `%TEMP%/bovo-docs/`.
- **RemoteUser** : ajout du champ `last_login`.
- `main.py` passe `client=client` à `BovoApp()`.
- **Tests** : 47/47 pytest ✅ + smoke_test_gui.py ✅ + repro_remember_gui.py ✅
  (testing agent iter 2 validé 100%).

### V1.4 (2026-07-01) — Bug fix « Se souvenir de moi »
- **RCA** : sous Windows (antivirus agressif), le WAL SQLite était perdu à la fermeture ⇒
  refresh_token jamais persisté. `Database.close()` force désormais un
  `PRAGMA wal_checkpoint(TRUNCATE)` avant fermeture.
- `RemoteAuthService.try_auto_login` distingue maintenant :
  - HTTP 401/403 (token expiré/révoqué) → renvoie `None`, appelant purge.
  - Erreur réseau / 5xx (serveur down) → lève `AutoLoginNetworkError`,
    appelant NE purge PAS, on retombe seulement sur le login manuel.
- `main._launch_login` catch `AutoLoginNetworkError` séparément (token conservé).
- `LoginDialog._attempt_login` : logs détaillés + relecture post-écriture du
  refresh_token pour diagnostiquer toute défaillance en prod chez l'utilisateur.
- Tests pytest ajoutés : `tests/test_remember_me.py` (6/6 PASS) + repro
  end-to-end xvfb `/tmp/repro_remember_gui.py`. Suite totale : **47/47 PASS**.

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

### Itération 5b — Déploiement Windows + portabilité VPS (2026-07-01)

### Itération 6 — Refactor client REST + icônes (2026-07-01)

**Objectif** : remplacer l'authentification locale bcrypt par l'API FastAPI centralisée et supprimer toute dépendance SQLite pour l'authentification.

**Livrables ajoutés côté client (`/app/bovo/`)** :

- **`app/session.py`** — `Session` + `RemoteUser` : encapsule l'utilisateur connecté et expose les permissions (`can_edit`, `can_view_planning`, `can_manage_users`, `can_view_audit`).
- **`app/remote_services.py`** — adaptateurs REST miroir des services locaux : `RemoteAuthService`, `RemotePlanner`, `RemoteInspectionService`, `RemoteDocumentService`, `RemoteAuditService`.
- **`app/server_config_dialog.py`** — écran de configuration serveur au premier lancement (URL + bouton « Tester la connexion » via `/api/health`).
- **`app/icons_generator.py`** — générateur PIL de 10 icônes PNG (maison, calendrier, loupe, outil, document, upload, horloge, users, journal, engrenage) en variantes rouge + blanche. Reproductible via `python -m app.icons_generator`.
- **`assets/icons/*.png`** — 20 fichiers (10 icônes × 2 variantes).
- **`main.py`** — réécrit : instance UNIQUE d'`ApiClient` partagée, `Session` en mémoire, `RemoteAuthService` drop-in, `SseListener` démarré après connexion, écran de config serveur si URL absente.

**Points clés**
- **Une seule instance** d'`ApiClient` créée au démarrage et partagée dans toute l'app.
- Le `LoginDialog` appelle `client.login(username, password)` via `RemoteAuthService` (drop-in de `AuthService`).
- « Se souvenir de moi » stocke désormais le **refresh token JWT** (au lieu du hash bcrypt legacy).
- `SseListener` démarre après connexion et rafraîchit la vue active automatiquement quand un autre poste modifie une entité (mapping entité → vues affectées).
- Aucun accès SQLite pour l'auth ; seuls le journal local, les settings et les paramètres restent en SQLite (fichier `bovo.db` par poste).
- Compatibilité `RemoteUser.role` (str) et `Role` enum (`.value`) via helper `BovoApp._role_label`.

**Validation**
- 41 tests pytest OK (dont test refresh token migration)
- Ruff 0 erreur sur `/app/bovo/` et `/app/bovo-server/`
- E2E validé contre backend mock : login OK, login KO, auto-login refresh, refresh invalide → tous les cas testés
- GUI complète rendue (10 nav items + 10 icônes chargées) après auth REST
- Handler SSE `_on_remote_event` testé sans crash

**Backlog restant P0**
- Refactor complet des vues GUI pour utiliser `RemoteServices` (actuellement `BovoApp` instancie encore Planner/InspectionService/DocumentService locaux — le login via API fonctionne, mais les données métier passent encore par SQLite)
- Écran Paramètres : bouton « Modifier URL serveur » qui ouvre `ServerConfigDialog`
- Indicateur d'état SSE dans la sidebar (🟢/🔴)
- Packaging PyInstaller `.exe` Windows

**Objectif** : déployer le backend FastAPI + PostgreSQL sur un PC Windows du
réseau BOVO qui reste allumé, avec démarrage automatique au boot, tout en
garantissant une migration ultérieure vers un VPS sans modification de code.

**Livrables ajoutés dans `/app/bovo-server/`** :

- **`DEPLOY_WINDOWS.md`** : guide de déploiement pas-à-pas — deux approches
  (Docker Desktop recommandé + installation native NSSM) avec prérequis,
  ouverture pare-feu, session dédiée `bovo-server`, IP statique.
- **`windows/install-docker.ps1`** : script d'installation automatique pour
  Docker Desktop. Installe Git + Docker Desktop via winget, génère un
  `.env` sécurisé (JWT random 32 octets), ouvre le port 8000 dans le
  pare-feu, lance la pile, vérifie `/api/health` (health-loop 60 s max).
- **`windows/install-native.ps1`** : installation native sans Docker.
  Installe Python 3.12 + PostgreSQL 16 (service Windows) + NSSM,
  provisionne la base `bovo`, crée le venv, enregistre le service
  `BovoASFManager` qui **démarre avant l'ouverture de session** (headless).
- **`windows/backup.ps1`** : dump `pg_dump` gzip + archive documents,
  rétention configurable, prêt pour le Planificateur de tâches Windows
  (exemple `schtasks` fourni).
- **`windows/status.ps1`** : diagnostic rapide (IP LAN, health API, état
  services, dernières logs, espace disque).
- **`windows/migrate-to-vps.ps1`** : génère une archive zip complète
  (code + `.env` + dump SQL + documents) prête à téléverser sur un VPS
  Linux. Aucune modification de code — même `docker compose up -d` sur
  Linux, restauration `psql <dump.sql`.
- **`docker-compose.override.yml.example`** : template pour rediriger
  volumes (backups vers NAS, port 80, etc.) sans toucher au compose
  principal.

**Validation**
- Syntaxe PowerShell 5 scripts validée via `pwsh 7.6.3` (`[Parser]::ParseFile`)
- Backend démarre sans erreur avec vars d'env minimales
- 41 tests pytest client + 0 erreur Ruff sur toute la codebase

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
