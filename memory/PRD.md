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

### Itération 4 — Backlog P2 : Auth, Audit, Carte, Documents (2026-07-01)
- **Auth locale bcrypt** (coût 12) : 3 comptes seedés idempotents
  (Admin/Planificateur/Consultant). Écran de connexion animé au démarrage,
  session mémoire, verrouillage après 5 échecs.
- **Rôles & permissions** : le Consultant n'a pas accès au Planning
  (Calendrier / Interventions / Importer PDF) ; boutons Ajouter/Supprimer
  masqués pour lui ; Admin seul voit « Utilisateurs ».
- **Historique des modifications** (audit trail) : table `audit_log` avec
  before/after JSON par entité (intervention, inspections, rapports, incidents,
  materiel, document). Vue Historique avec filtre par entité + recherche.
  `AuditEntry.diff()` filtre les champs meta (id, created_at, updated_at).
- **Carte interactive** OpenStreetMap via `tkintermapview` (offline tiles),
  marqueurs bâtis depuis latitude/longitude des rapports. Centrée sur
  Toulouse par défaut.
- **Gestion documentaire** : attacher PDF/PNG/JPEG/DOCX/XLSX à une entité,
  stockage local (`bovo/documents/<AAAA>/<uuid>.<ext>`) référencé en base.
  Ouverture native + suppression.
- **Écran Utilisateurs** (Admin) : création + changement de mot de passe +
  suppression (sauf soi-même).
- **Sync réseau** : reporté (option D non retenue par le client).
- Bandeau utilisateur en pied de sidebar + bouton « Se déconnecter ».
- 38 tests pytest OK (7 nouveaux — auth × 4, audit × 2, documents × 1) ;
  Ruff 0 erreur ; smoke GUI Xvfb OK sur les 3 rôles.

### Comptes seedés
Voir `/app/memory/test_credentials.md`.

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
