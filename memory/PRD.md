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
logger,settings,utils}.py · database/bovo.db · assets/logo.png · tests/.
GUI sans logique métier ; logique répartie dans les modules.

## Implémenté (V1 — 2026-06-30)
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
