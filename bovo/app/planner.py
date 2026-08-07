"""Chef d'orchestre métier de Bovo ASF Manager.

``planner.py`` coordonne l'ensemble du pipeline :

    PDF(s) / dossier  →  PdfParser  →  upsert SQLite (dédoublonnage par ouvrage)
                      →  statistiques  →  données pour le calendrier.

Les imports peuvent être suivis via un callback de progression, ce qui permet
au GUI d'afficher une barre de progression sans contenir de logique métier.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from typing import Any

from app.calendar import CalendarModel
from app.database import Database
from app.logger import LogAction, LogLevel, get_logger, log_action
from app.models import Intervention, ParsedIntervention, PdfFile, StatutIntervention
from app.parser_pdf import PdfParser

logger = get_logger("planner")

ProgressCallback = Callable[[int, int, str], None]


@dataclass(slots=True)
class ImportResult:
    """Synthèse d'une opération d'import."""

    files_processed: int = 0
    interventions_created: int = 0
    interventions_updated: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_interventions(self) -> int:
        """Nombre total d'interventions traitées (créées + mises à jour)."""
        return self.interventions_created + self.interventions_updated

    def merge(self, other: ImportResult) -> None:
        """Fusionne un autre résultat dans celui-ci."""
        self.files_processed += other.files_processed
        self.interventions_created += other.interventions_created
        self.interventions_updated += other.interventions_updated
        self.errors.extend(other.errors)


class Planner:
    """Orchestrateur central reliant parser, base, statistiques et calendrier."""

    def __init__(self, database: Database, audit: Any | None = None) -> None:
        """Initialise l'orchestrateur avec une base et ses dépendances.

        Args:
            database: Instance :class:`Database` partagée.
            audit: :class:`AuditService` optionnel pour l'historique.
        """
        self._db = database
        self._parser = PdfParser()
        self._calendar = CalendarModel()
        self._audit = audit

    # ------------------------------------------------------------------ #
    # Imports
    # ------------------------------------------------------------------ #
    def import_pdf(
        self, pdf_path: Path, progress: ProgressCallback | None = None
    ) -> ImportResult:
        """Importe un unique PDF."""
        return self.import_pdfs([pdf_path], progress)

    def import_folder(
        self, folder: Path, progress: ProgressCallback | None = None
    ) -> ImportResult:
        """Importe tous les PDF d'un dossier (récursivement)."""
        pdfs = sorted(folder.rglob("*.pdf"))
        if not pdfs:
            log_action(
                self._db,
                LogAction.IMPORT,
                f"Aucun PDF trouvé dans {folder}",
                level=LogLevel.WARNING,
            )
        return self.import_pdfs(pdfs, progress)

    def import_pdfs(
        self, pdf_paths: list[Path], progress: ProgressCallback | None = None
    ) -> ImportResult:
        """Importe une liste de PDF, met à jour la base et journalise.

        Args:
            pdf_paths: Chemins des PDF à traiter.
            progress: Callback ``(courant, total, message)`` optionnel.

        Returns:
            Le :class:`ImportResult` agrégé.
        """
        result = ImportResult()
        total = len(pdf_paths)
        for idx, pdf_path in enumerate(pdf_paths, start=1):
            if progress is not None:
                progress(idx, total, f"Analyse de {pdf_path.name}")
            try:
                file_result = self._import_single(pdf_path)
                result.merge(file_result)
            except Exception as exc:  # noqa: BLE001 - on isole chaque fichier.
                message = f"Échec import {pdf_path.name} : {exc}"
                result.errors.append(message)
                log_action(self._db, LogAction.ERROR, message, level=LogLevel.ERROR)
                logger.exception("Erreur lors de l'import de %s", pdf_path)
        return result

    def _import_single(self, pdf_path: Path) -> ImportResult:
        """Traite un seul PDF (parser + upsert + métadonnées)."""
        result = ImportResult(files_processed=1)
        parsed_list = self._parser.parse_file(pdf_path)
        for parsed in parsed_list:
            intervention = self._to_intervention(parsed)
            _, created = self._db.upsert_intervention(intervention)
            if created:
                result.interventions_created += 1
            else:
                result.interventions_updated += 1

        self._db.upsert_pdf(
            PdfFile(
                name=pdf_path.name,
                path=str(pdf_path),
                interventions_count=len(parsed_list),
                imported_at=datetime.now(UTC).isoformat(),
            )
        )
        log_action(
            self._db,
            LogAction.IMPORT,
            f"{pdf_path.name} importé : {len(parsed_list)} intervention(s) "
            f"({result.interventions_created} créées, "
            f"{result.interventions_updated} mises à jour).",
            level=LogLevel.SUCCESS,
        )
        return result

    @staticmethod
    def _to_intervention(parsed: ParsedIntervention) -> Intervention:
        """Convertit un résultat de parsing en entité persistable."""
        statut = (
            StatutIntervention.PLANIFIEE
            if parsed.dates
            else StatutIntervention.A_FAIRE
        )
        return Intervention(
            ouvrage=parsed.ouvrage,
            objet=parsed.objet,
            autoroute=parsed.autoroute,
            secteur=parsed.secteur,
            pr_debut=parsed.pr_debut,
            pr_fin=parsed.pr_fin,
            sens=parsed.sens,
            longueur=parsed.longueur,
            diametre=parsed.diametre,
            type_ouvrage=parsed.type_ouvrage,
            date_debut=parsed.date_debut,
            date_fin=parsed.date_fin,
            statut=statut,
            pdf_path=parsed.pdf_path,
            commentaire=parsed.observations,
        )

    # ------------------------------------------------------------------ #
    # Données pour le GUI
    # ------------------------------------------------------------------ #
    def get_statistics(self) -> dict[str, object]:
        """Retourne les statistiques du tableau de bord."""
        return self._db.statistics()

    def search(
        self,
        *,
        search: str = "",
        statut: str = "",
        autoroute: str = "",
        secteur: str = "",
    ) -> list[Intervention]:
        """Recherche instantanée multi-critères."""
        return self._db.list_interventions(
            search=search, statut=statut, autoroute=autoroute, secteur=secteur
        )

    def build_calendar(self, year: int, month: int) -> list:
        """Construit la grille du calendrier pour un mois donné."""
        first = f"{year:04d}-{month:02d}-01"
        last = f"{year:04d}-{month:02d}-31"
        interventions = self._db.list_interventions_between(first, last)
        return self._calendar.build_month(year, month, interventions)

    def filter_options(self) -> dict[str, list[str]]:
        """Retourne les valeurs distinctes pour alimenter les filtres du GUI."""
        return {
            "autoroutes": self._db.distinct_values("autoroute"),
            "secteurs": self._db.distinct_values("secteur"),
            "statuts": [s.value for s in StatutIntervention],
        }

    def set_statut(self, intervention_id: int, statut: StatutIntervention) -> None:
        """Met à jour le statut d'une intervention et journalise."""
        before = self._db.get_intervention_by_id(intervention_id)
        before_data = {"statut": before.statut.value} if before else {}
        self._db.update_intervention_fields(intervention_id, statut=statut.value)
        log_action(
            self._db,
            LogAction.UPDATE,
            f"Statut de l'intervention #{intervention_id} → {statut.value}",
        )
        if self._audit is not None:
            self._audit.record(
                action="update", entity="intervention",
                entity_id=str(intervention_id),
                before=before_data, after={"statut": statut.value},
            )

    def delete(self, intervention_id: int) -> None:
        """Supprime une intervention et journalise."""
        before = self._db.get_intervention_by_id(intervention_id)
        self._db.delete_intervention(intervention_id)
        log_action(
            self._db,
            LogAction.DELETE,
            f"Intervention #{intervention_id} supprimée.",
            level=LogLevel.WARNING,
        )
        if self._audit is not None:
            self._audit.record(
                action="delete", entity="intervention",
                entity_id=str(intervention_id),
                before=before.to_row() if before else {}, after={},
            )
