# BOVO Planning Manager

Logiciel professionnel de gestion automatique des interventions ASF réalisées
par **BOVO & FILS**. L'utilisateur sélectionne un ou plusieurs PDF de listing
d'ouvrages : le logiciel lit les PDF, extrait toutes les informations utiles,
crée ou met à jour les interventions en base SQLite, puis met automatiquement à
jour le planning et le calendrier interactif.

> Développé par **HENRI Dylan**.

## Technologies

Python 3.12+, CustomTkinter, SQLite3, PyMuPDF (fitz), Pillow, openpyxl, ainsi
que les modules standards `pathlib`, `dataclasses`, `typing`, `logging`,
`threading`, `queue`, `json`, `os`, `shutil`, `re`, `datetime`, `calendar`.

## Architecture

```
bovo/
├── main.py                 # Point d'entrée : splash + application
├── requirements.txt
├── pyproject.toml          # Config Ruff / Flake8 / MyPy / Pytest
├── app/
│   ├── __init__.py
│   ├── gui.py              # Interface CustomTkinter (aucune logique métier)
│   ├── database.py         # Couche SQLite (CRUD, doublons, statistiques)
│   ├── models.py           # Dataclasses + énumérations
│   ├── parser_pdf.py       # Extraction tabulaire + parsing des dates
│   ├── planner.py          # Chef d'orchestre (import, dédoublonnage, stats)
│   ├── calendar.py         # Modèle de calendrier mensuel
│   ├── exporter.py         # Exports Excel / CSV / JSON / PDF
│   ├── logger.py           # Journalisation fichier + base
│   ├── settings.py         # Paramètres persistés
│   └── utils.py            # Utilitaires transverses
├── assets/                 # logo.png (logo BOVO & FILS)
├── database/               # bovo.db (créé au premier lancement)
├── exports/                # exports générés
├── logs/                   # journaux applicatifs
├── sample/                 # PDF d'exemple
└── tests/                  # tests pytest
```

## Installation

```bash
cd bovo
python -m venv .venv
# Windows : .venv\Scripts\activate   |   macOS/Linux : source .venv/bin/activate
pip install -r requirements.txt
```

## Lancement

```bash
python main.py
```

Au démarrage : splash animé (logo + « Développé par HENRI Dylan »), puis page
d'accueil « Bonjour {utilisateur} » et tableau de bord.

## Utilisation

1. **Importer PDF** : choisir un/plusieurs PDF ou un dossier complet. L'import
   s'effectue en arrière-plan avec barre de progression.
2. **Calendrier** : vue mensuelle, nombre d'interventions par jour, couleurs par
   statut, clic pour ouvrir la fiche détaillée (avec bouton « Ouvrir le PDF »).
   Une intervention dont un rapport ASF existe passe automatiquement « Terminée »
   (vert) ; le statut reste modifiable manuellement dans la fiche.
3. **Interventions** : recherche instantanée + filtres (statut, autoroute) et
   exports Excel / CSV / JSON / PDF.
4. **Inspections ASF (ITV)** : modules éditables directement dans le logiciel —
   *Inspections*, *Rapports d'inspection*, *Incidents*, *Matériel* — avec listes
   déroulantes issues du Référentiel. Bouton « Importer le classeur Excel » pour
   initialiser les données. Saisir un rapport pour un ouvrage marque
   automatiquement l'intervention correspondante comme « Terminée ».
5. **Journal** : historique complet des actions.
6. **Paramètres** : thème, sauvegarde automatique, dossiers.

Le tableau de bord recalcule les indicateurs ASF (ML inspectés, nombre
d'inspections, regards, heures totales, ML/h) à partir des inspections saisies.

## Formats de dates reconnus

`15/06/2026` · `15 et 16/07/2026` · `23 au 26/11/2026` ·
`27-28-29-30/07/2026` · `29-30/06/2026` · `nuits 22 et 23/06/2026`.

## Qualité

```bash
ruff check .
flake8 .
mypy app
pytest -q
```

## Évolutions prévues (architecture évolutive)

Multi-utilisateurs et rôles, historique des modifications, synchronisation
réseau, carte interactive des interventions, notifications, sauvegardes
automatiques, mises à jour logicielles, impression des plannings, tableau de
bord avancé, gestion documentaire et glisser-déposer de PDF.
