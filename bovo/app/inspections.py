"""Module métier des inspections ASF (ITV) de BOVO Planning Manager.

Gère les modules éditables issus du classeur Excel — Inspections, Rapports
d'inspection, Incidents et Matériel — entièrement dans le logiciel (plus besoin
d'Excel pour la saisie). Fournit également :

    * l'import initial du classeur Excel (seeding) ;
    * les listes de référence alimentant les menus déroulants ;
    * le recalcul des indicateurs (KPIs) du tableau de bord ;
    * la complétion automatique des interventions : dès qu'un rapport existe
      pour un ouvrage (champ « Identifiant »), l'intervention correspondante
      passe au statut « Terminée ».

Aucune logique d'affichage ici : le GUI consomme uniquement ce service.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import openpyxl

from app.database import Database
from app.logger import LogAction, LogLevel, get_logger, log_action
from app.models import StatutIntervention

logger = get_logger("inspections")


@dataclass(slots=True, frozen=True)
class FieldSpec:
    """Description d'un champ de formulaire pour un module."""

    column: str
    label: str
    widget: str = "text"  # text | number | date | long | choice
    ref_key: str = ""


# Colonnes des tables, dans l'ordre exact des colonnes du classeur Excel.
ORDERED_COLUMNS: dict[str, list[str]] = {
    "inspections": [
        "n_inspection", "date", "jour_nuit", "autoroute", "secteur",
        "pk_depart", "pk_arrivee", "ml_inspectes", "nb_regards",
        "heure_debut", "heure_fin", "heures_totales", "ml_h",
        "operateur", "coequipier", "meteo", "observations",
    ],
    "rapports": [
        "date", "identifiant", "n_inspection", "prestataire", "inspecteur",
        "autoroute", "type_ouvrage", "secteur", "sens", "emplacement",
        "type_materiau", "latitude", "longitude", "lien_maps", "requalif",
        "etat_cunettes", "type_defaut", "urgence", "description", "photo",
        "statut",
    ],
    "incidents": [
        "date", "autoroute", "pk", "type_incident", "description",
        "impact", "action_prise",
    ],
    "materiel": [
        "date", "camera", "chariot", "vehicule", "km_depart", "km_arrivee",
        "entretien", "panne", "observations",
    ],
}

SHEET_LABELS: dict[str, str] = {
    "inspections": "Inspections",
    "rapports": "Rapports d'inspection",
    "incidents": "Incidents",
    "materiel": "Matériel",
}

# Noms des feuilles dans le classeur Excel source.
EXCEL_SHEET_NAMES: dict[str, str] = {
    "inspections": "Inspections",
    "rapports": "Rapport d'Inspections",
    "incidents": "Incidents",
    "materiel": "Matériel",
}

FORM_FIELDS: dict[str, list[FieldSpec]] = {
    "inspections": [
        FieldSpec("n_inspection", "N° Inspection", "text"),
        FieldSpec("date", "Date", "date"),
        FieldSpec("jour_nuit", "Jour/Nuit", "choice", "choix_jour"),
        FieldSpec("autoroute", "Autoroute", "choice", "autoroutes"),
        FieldSpec("secteur", "Secteur", "choice", "secteur"),
        FieldSpec("pk_depart", "PK Départ", "text"),
        FieldSpec("pk_arrivee", "PK Arrivée", "text"),
        FieldSpec("ml_inspectes", "ML Inspectés", "number"),
        FieldSpec("nb_regards", "Nb Regards", "number"),
        FieldSpec("heure_debut", "Heure Début", "text"),
        FieldSpec("heure_fin", "Heure Fin", "text"),
        FieldSpec("heures_totales", "Heures Totales", "number"),
        FieldSpec("operateur", "Opérateur", "choice", "operateurs_itv"),
        FieldSpec("coequipier", "Coéquipier", "choice", "operateurs_hydro"),
        FieldSpec("meteo", "Météo", "choice", "meteo"),
        FieldSpec("observations", "Observations", "long"),
    ],
    "rapports": [
        FieldSpec("date", "Date", "date"),
        FieldSpec("identifiant", "Identifiant (Ouvrage)", "text"),
        FieldSpec("n_inspection", "N° Inspection", "text"),
        FieldSpec("prestataire", "Prestataire", "text"),
        FieldSpec("inspecteur", "Inspecteur", "choice", "operateurs_itv"),
        FieldSpec("autoroute", "Autoroute", "choice", "autoroutes"),
        FieldSpec("type_ouvrage", "Type", "choice", "type"),
        FieldSpec("secteur", "Secteur", "choice", "secteur"),
        FieldSpec("sens", "Sens", "text"),
        FieldSpec("emplacement", "Emplacement", "text"),
        FieldSpec("type_materiau", "Type de matériau", "choice", "type_materiau"),
        FieldSpec("latitude", "Latitude", "text"),
        FieldSpec("longitude", "Longitude", "text"),
        FieldSpec("lien_maps", "Lien Maps", "text"),
        FieldSpec("requalif", "Si objet à requalifier", "choice", "requalif"),
        FieldSpec("etat_cunettes", "État général des cunettes", "choice", "etat_cunettes"),
        FieldSpec("type_defaut", "Type de défaut", "text"),
        FieldSpec("urgence", "Urgence", "choice", "urgence"),
        FieldSpec("description", "Description", "long"),
        FieldSpec("photo", "Photo", "text"),
        FieldSpec("statut", "Statut", "text"),
    ],
    "incidents": [
        FieldSpec("date", "Date", "date"),
        FieldSpec("autoroute", "Autoroute", "choice", "autoroutes"),
        FieldSpec("pk", "PK", "text"),
        FieldSpec("type_incident", "Type Incident", "text"),
        FieldSpec("description", "Description", "long"),
        FieldSpec("impact", "Impact", "text"),
        FieldSpec("action_prise", "Action prise", "long"),
    ],
    "materiel": [
        FieldSpec("date", "Date", "date"),
        FieldSpec("camera", "Caméra", "choice", "camera"),
        FieldSpec("chariot", "Chariot", "choice", "chariot"),
        FieldSpec("vehicule", "Véhicule", "choice", "vehicules"),
        FieldSpec("km_depart", "Km Départ", "text"),
        FieldSpec("km_arrivee", "Km Arrivée", "text"),
        FieldSpec("entretien", "Entretien", "text"),
        FieldSpec("panne", "Panne", "choice", "panne"),
        FieldSpec("observations", "Observations", "long"),
    ],
}

# Colonnes affichées dans les tableaux récapitulatifs de chaque module.
LIST_COLUMNS: dict[str, list[str]] = {
    "inspections": ["n_inspection", "date", "autoroute", "secteur", "ml_inspectes", "operateur"],
    "rapports": ["date", "identifiant", "autoroute", "type_ouvrage", "secteur", "urgence"],
    "incidents": ["date", "autoroute", "pk", "type_incident", "impact"],
    "materiel": ["date", "camera", "vehicule", "panne", "entretien"],
}

# Listes de référence par défaut (utilisées tant que le classeur n'est pas importé).
DEFAULT_REFERENTIEL: dict[str, list[str]] = {
    "operateurs_itv": ["Hugo D.", "Dylan H."],
    "operateurs_hydro": [
        "Ludovic B.", "Amadou B.", "Dylan P.", "Exaucé", "Pierre",
        "Tristan", "Yassine", "Baptiste", "Yohan",
    ],
    "meteo": ["Beau", "Pluvieux", "Nuageux", "Orageux", "Neigeux"],
    "choix_jour": ["Jour", "Nuit"],
    "secteur": ["Midi Toulousain", "Garonne", "Agen", "Quercy"],
    "autoroutes": ["A61", "A66", "A68", "A62", "A20", "A64"],
    "type": ["CA", "OH", "DE"],
    "type_materiau": ["Enherbé", "Métallique", "Mixte", "Béton", "Autre"],
    "urgence": ["Aucune", "Moindre", "Moyenne", "Elevée", "Très elevée"],
    "requalif": [
        "Non", "Cunette revêtue - Béton", "Cunette revêtue - autre matériau",
        "Cunette non revêtue", "Fossé revêtu - Béton",
        "Fossé revêtu - Autre matériau", "Fossé non revêtu",
        "Descente d'eau enterrée", "Descente d'eau superficielle",
        "Collecteur enterré", "Caniveau ouvert", "Caniveau à fente",
    ],
    "etat_cunettes": [
        "Pas de défauts", "Non évolutif", "Evolution normale",
        "Défauts majeurs", "Non visitable",
    ],
    "camera": ["IBAK Orpheus 2", "IBAK Nano", "IBAK Nano L", "IBAK Orion 3"],
    "chariot": ["T76.2", "T66.1"],
    "vehicules": ["Sprinter 41", "Citan 55"],
    "panne": ["Aucune", "Oui"],
}

# Index des colonnes du Référentiel Excel → clé de référence.
_REFERENTIEL_COLUMN_MAP: dict[int, str] = {
    1: "operateurs_itv", 2: "operateurs_hydro", 4: "meteo", 6: "choix_jour",
    7: "secteur", 8: "autoroutes", 9: "type", 10: "type_materiau",
    11: "urgence", 12: "requalif", 13: "etat_cunettes", 16: "camera",
    17: "chariot", 18: "vehicules", 19: "panne",
}


def _cell_to_str(value: Any) -> str:
    """Convertit une valeur de cellule Excel en chaîne stockable."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M:%S")
    if isinstance(value, float):
        return str(round(value, 3))
    return str(value).strip()


def _to_float(value: str) -> float:
    """Convertit une chaîne en flottant, ou 0.0 si impossible."""
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return 0.0


class InspectionService:
    """Service applicatif des modules ASF (CRUD, import Excel, KPIs, liaisons)."""

    SHEETS: tuple[str, ...] = ("inspections", "rapports", "incidents", "materiel")

    def __init__(self, database: Database) -> None:
        """Initialise le service et garantit l'existence des tables."""
        self._db = database
        self._db.ensure_tables_from_specs(ORDERED_COLUMNS)
        self._referentiel = self._load_referentiel()

    # ------------------------------------------------------------------ #
    # Référentiel
    # ------------------------------------------------------------------ #
    def _load_referentiel(self) -> dict[str, list[str]]:
        """Charge le référentiel depuis les paramètres, sinon les défauts."""
        stored = self._db.get_setting("referentiel")
        if stored:
            try:
                data = json.loads(stored)
                merged = dict(DEFAULT_REFERENTIEL)
                merged.update({k: v for k, v in data.items() if v})
                return merged
            except json.JSONDecodeError:
                logger.warning("Référentiel stocké illisible, utilisation des défauts.")
        return dict(DEFAULT_REFERENTIEL)

    def referentiel(self, ref_key: str) -> list[str]:
        """Retourne la liste de référence associée à une clé."""
        return self._referentiel.get(ref_key, [])

    # ------------------------------------------------------------------ #
    # Métadonnées de structure (consommées par le GUI)
    # ------------------------------------------------------------------ #
    @staticmethod
    def sheet_label(sheet: str) -> str:
        """Libellé lisible d'un module."""
        return SHEET_LABELS[sheet]

    @staticmethod
    def form_fields(sheet: str) -> list[FieldSpec]:
        """Champs de formulaire d'un module."""
        return FORM_FIELDS[sheet]

    @staticmethod
    def list_columns(sheet: str) -> list[tuple[str, str]]:
        """Colonnes (clé, libellé) affichées dans le tableau d'un module."""
        labels = {f.column: f.label for f in FORM_FIELDS[sheet]}
        return [(col, labels.get(col, col)) for col in LIST_COLUMNS[sheet]]

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #
    def list_rows(self, sheet: str, search: str = "") -> list[dict[str, str]]:
        """Liste les lignes d'un module."""
        return self._db.list_generic(sheet, search)

    def get_row(self, sheet: str, row_id: int) -> dict[str, str] | None:
        """Retourne une ligne d'un module par son id."""
        return self._db.get_generic(sheet, row_id)

    def save_row(
        self, sheet: str, data: dict[str, str], row_id: int | None = None
    ) -> int:
        """Crée ou met à jour une ligne, puis déclenche les liaisons éventuelles.

        Returns:
            L'identifiant de la ligne enregistrée.
        """
        if row_id is None:
            new_id = self._db.insert_generic(sheet, data)
            log_action(
                self._db, LogAction.CREATE,
                f"{SHEET_LABELS[sheet]} : nouvelle entrée #{new_id}.",
            )
        else:
            self._db.update_generic(sheet, row_id, data)
            new_id = row_id
            log_action(
                self._db, LogAction.UPDATE,
                f"{SHEET_LABELS[sheet]} : entrée #{row_id} modifiée.",
            )
        if sheet == "rapports":
            self._mark_intervention_done(data.get("identifiant", ""))
        return new_id

    def delete_row(self, sheet: str, row_id: int) -> None:
        """Supprime une ligne d'un module."""
        self._db.delete_generic(sheet, row_id)
        log_action(
            self._db, LogAction.DELETE,
            f"{SHEET_LABELS[sheet]} : entrée #{row_id} supprimée.",
            level=LogLevel.WARNING,
        )

    # ------------------------------------------------------------------ #
    # Liaison rapport → intervention
    # ------------------------------------------------------------------ #
    def _mark_intervention_done(self, identifiant: str) -> int:
        """Passe l'intervention liée au statut « Terminée ». Retourne 1 si traité."""
        identifiant = (identifiant or "").strip()
        if not identifiant:
            return 0
        intervention = self._db.get_intervention_by_ouvrage(identifiant)
        if intervention is None or intervention.id is None:
            return 0
        if intervention.statut is StatutIntervention.TERMINEE:
            return 0
        self._db.update_intervention_fields(
            intervention.id, statut=StatutIntervention.TERMINEE.value
        )
        log_action(
            self._db, LogAction.UPDATE,
            f"Intervention {identifiant} marquée « Terminée » (rapport ASF).",
            level=LogLevel.SUCCESS,
        )
        return 1

    def synchronize_interventions(self) -> int:
        """Re-synchronise toutes les interventions à partir des rapports existants."""
        count = 0
        for rapport in self._db.list_generic("rapports"):
            count += self._mark_intervention_done(rapport.get("identifiant", ""))
        return count

    # ------------------------------------------------------------------ #
    # KPIs (recalcul du tableau de bord Excel)
    # ------------------------------------------------------------------ #
    def kpis(self) -> dict[str, str]:
        """Recalcule les indicateurs ASF à partir des inspections."""
        rows = self._db.list_generic("inspections")
        total_ml = sum(_to_float(r.get("ml_inspectes", "")) for r in rows)
        total_regards = sum(_to_float(r.get("nb_regards", "")) for r in rows)
        total_heures = sum(_to_float(r.get("heures_totales", "")) for r in rows)
        ml_h = total_ml / total_heures if total_heures else 0.0
        return {
            "ml_inspectes": f"{total_ml:,.0f}".replace(",", " "),
            "nb_inspections": str(len(rows)),
            "regards": f"{total_regards:,.0f}".replace(",", " "),
            "heures": f"{total_heures:.1f}",
            "ml_h": f"{ml_h:.1f}",
        }

    # ------------------------------------------------------------------ #
    # Import du classeur Excel
    # ------------------------------------------------------------------ #
    def import_workbook(self, path: Path) -> dict[str, int]:
        """Importe le classeur ASF dans SQLite (remplace les données existantes).

        Args:
            path: Chemin du fichier ``.xlsx``.

        Returns:
            Un récapitulatif ``{module: nombre_de_lignes}``.

        Raises:
            FileNotFoundError: Si le fichier est introuvable.
        """
        if not path.exists():
            raise FileNotFoundError(f"Classeur introuvable : {path}")
        workbook = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
        summary: dict[str, int] = {}
        try:
            self._import_referentiel(workbook)
            for sheet, excel_name in EXCEL_SHEET_NAMES.items():
                if excel_name not in workbook.sheetnames:
                    summary[sheet] = 0
                    continue
                summary[sheet] = self._import_sheet(workbook[excel_name], sheet)
        finally:
            workbook.close()

        linked = self.synchronize_interventions()
        log_action(
            self._db, LogAction.IMPORT,
            f"Classeur ASF importé : {summary} · {linked} intervention(s) liée(s).",
            level=LogLevel.SUCCESS,
        )
        summary["interventions_liees"] = linked
        return summary

    def _import_sheet(self, worksheet: Any, sheet: str) -> int:
        """Importe une feuille Excel dans la table correspondante."""
        columns = ORDERED_COLUMNS[sheet]
        anchor = "date" if "date" in columns else columns[0]
        anchor_index = columns.index(anchor)
        self._db.clear_table(sheet)
        inserted = 0
        for row_index, row in enumerate(worksheet.iter_rows(values_only=True)):
            if row_index == 0:
                continue  # ligne d'en-tête
            values = list(row)
            anchor_value = values[anchor_index] if anchor_index < len(values) else None
            if anchor_value in (None, ""):
                continue  # ligne-modèle vide (pas de date réelle)
            data = {
                columns[i]: _cell_to_str(values[i])
                for i in range(min(len(columns), len(values)))
            }
            self._db.insert_generic(sheet, data)
            inserted += 1
        return inserted

    def _import_referentiel(self, workbook: Any) -> None:
        """Extrait les listes de référence du classeur et les persiste."""
        if "Référentiel" not in workbook.sheetnames:
            return
        worksheet = workbook["Référentiel"]
        collected: dict[str, list[str]] = {key: [] for key in _REFERENTIEL_COLUMN_MAP.values()}
        for row_index, row in enumerate(worksheet.iter_rows(values_only=True)):
            if row_index == 0:
                continue
            for col_index, ref_key in _REFERENTIEL_COLUMN_MAP.items():
                cell = row[col_index - 1] if col_index - 1 < len(row) else None
                text = _cell_to_str(cell)
                if text and text not in collected[ref_key]:
                    collected[ref_key].append(text)
        merged = dict(DEFAULT_REFERENTIEL)
        merged.update({k: v for k, v in collected.items() if v})
        self._referentiel = merged
        self._db.set_setting("referentiel", json.dumps(merged, ensure_ascii=False))


__all__ = ["FieldSpec", "InspectionService"]
