"""Modèles de données de Bovo ASF Manager.

Définit les entités métier sous forme de :mod:`dataclasses` entièrement typées
ainsi que les énumérations associées. Chaque modèle propose des helpers de
sérialisation (``to_row`` / ``from_row``) pour dialoguer avec SQLite sans
fuite de la couche de persistance dans le reste du code.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any


class StatutIntervention(StrEnum):
    """Statuts possibles d'une intervention ASF."""

    A_FAIRE = "À faire"
    PLANIFIEE = "Planifiée"
    EN_COURS = "En cours"
    TERMINEE = "Terminée"
    ANNULEE = "Annulée"

    @classmethod
    def from_value(cls, value: str | None) -> StatutIntervention:
        """Retourne le statut correspondant, ou ``A_FAIRE`` par défaut."""
        if not value:
            return cls.A_FAIRE
        for statut in cls:
            if statut.value == value or statut.name == value:
                return statut
        return cls.A_FAIRE


def _now_iso() -> str:
    """Horodatage ISO 8601 en UTC."""
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class Intervention:
    """Représente une intervention ASF réalisée ou planifiée par BOVO."""

    ouvrage: str
    objet: str = ""
    autoroute: str = ""
    secteur: str = ""
    pr_debut: str = ""
    pr_fin: str = ""
    sens: str = ""
    longueur: str = ""
    diametre: str = ""
    type_ouvrage: str = ""
    date_debut: date | None = None
    date_fin: date | None = None
    statut: StatutIntervention = StatutIntervention.A_FAIRE
    pdf_path: str = ""
    commentaire: str = ""
    id: int | None = None
    created_at: str = field(default_factory=_now_iso)
    updated_at: str = field(default_factory=_now_iso)

    def to_row(self) -> dict[str, Any]:
        """Sérialise l'intervention en dictionnaire compatible SQLite."""
        return {
            "id": self.id,
            "ouvrage": self.ouvrage,
            "objet": self.objet,
            "autoroute": self.autoroute,
            "secteur": self.secteur,
            "pr_debut": self.pr_debut,
            "pr_fin": self.pr_fin,
            "sens": self.sens,
            "longueur": self.longueur,
            "diametre": self.diametre,
            "type_ouvrage": self.type_ouvrage,
            "date_debut": self.date_debut.isoformat() if self.date_debut else None,
            "date_fin": self.date_fin.isoformat() if self.date_fin else None,
            "statut": self.statut.value,
            "pdf_path": self.pdf_path,
            "commentaire": self.commentaire,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Intervention:
        """Reconstruit une intervention depuis une ligne SQLite."""

        def _to_date(value: Any) -> date | None:
            if not value:
                return None
            try:
                return date.fromisoformat(str(value)[:10])
            except ValueError:
                return None

        return cls(
            id=row.get("id"),
            ouvrage=row.get("ouvrage", ""),
            objet=row.get("objet", ""),
            autoroute=row.get("autoroute", ""),
            secteur=row.get("secteur", ""),
            pr_debut=row.get("pr_debut", ""),
            pr_fin=row.get("pr_fin", ""),
            sens=row.get("sens", ""),
            longueur=row.get("longueur", ""),
            diametre=row.get("diametre", ""),
            type_ouvrage=row.get("type_ouvrage", ""),
            date_debut=_to_date(row.get("date_debut")),
            date_fin=_to_date(row.get("date_fin")),
            statut=StatutIntervention.from_value(row.get("statut")),
            pdf_path=row.get("pdf_path", ""),
            commentaire=row.get("commentaire", ""),
            created_at=row.get("created_at", _now_iso()),
            updated_at=row.get("updated_at", _now_iso()),
        )


@dataclass(slots=True)
class PdfFile:
    """Métadonnées d'un PDF importé dans le logiciel."""

    name: str
    path: str
    interventions_count: int = 0
    imported_at: str = field(default_factory=_now_iso)
    id: int | None = None

    def to_row(self) -> dict[str, Any]:
        """Sérialise le PDF en dictionnaire compatible SQLite."""
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "interventions_count": self.interventions_count,
            "imported_at": self.imported_at,
        }

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> PdfFile:
        """Reconstruit un PDF depuis une ligne SQLite."""
        return cls(
            id=row.get("id"),
            name=row.get("name", ""),
            path=row.get("path", ""),
            interventions_count=int(row.get("interventions_count", 0) or 0),
            imported_at=row.get("imported_at", _now_iso()),
        )


@dataclass(slots=True)
class LogEntry:
    """Entrée du journal métier."""

    action: str
    level: str
    message: str
    created_at: str = field(default_factory=_now_iso)
    id: int | None = None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> LogEntry:
        """Reconstruit une entrée de log depuis une ligne SQLite."""
        return cls(
            id=row.get("id"),
            action=row.get("action", ""),
            level=row.get("level", "INFO"),
            message=row.get("message", ""),
            created_at=row.get("created_at", _now_iso()),
        )


@dataclass(slots=True)
class ParsedIntervention:
    """Résultat brut d'analyse d'un PDF avant insertion en base.

    Sépare clairement la sortie du parser (potentiellement multi-dates) de
    l'entité persistée :class:`Intervention`.
    """

    ouvrage: str
    objet: str = ""
    autoroute: str = ""
    secteur: str = ""
    pr_debut: str = ""
    pr_fin: str = ""
    sens: str = ""
    longueur: str = ""
    diametre: str = ""
    type_ouvrage: str = ""
    dates: list[date] = field(default_factory=list)
    observations: str = ""
    pdf_name: str = ""
    pdf_path: str = ""

    @property
    def date_debut(self) -> date | None:
        """Première date planifiée détectée."""
        return min(self.dates) if self.dates else None

    @property
    def date_fin(self) -> date | None:
        """Dernière date planifiée détectée."""
        return max(self.dates) if self.dates else None

    def field_names(self) -> list[str]:
        """Liste des champs de la dataclass (utilitaire de debug/tests)."""
        return [f.name for f in fields(self)]
