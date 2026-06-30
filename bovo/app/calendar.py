"""Modèle logique du calendrier mensuel de BOVO Planning Manager.

Construit la grille d'un mois et y projette les interventions par journée,
avec un code couleur dépendant du statut. Aucune dépendance GUI : ce module
fournit uniquement des structures de données prêtes à être affichées.

Note : ``import calendar`` fait référence au module standard (imports absolus
Python 3) et non à ce module ``app.calendar``.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date

from app.models import Intervention, StatutIntervention

# Couleurs (hex) associées à chaque statut, réutilisées par le GUI.
STATUT_COLORS: dict[StatutIntervention, str] = {
    StatutIntervention.A_FAIRE: "#E63946",
    StatutIntervention.PLANIFIEE: "#F4A261",
    StatutIntervention.EN_COURS: "#2A9D8F",
    StatutIntervention.TERMINEE: "#43AA8B",
    StatutIntervention.ANNULEE: "#6C757D",
}

MONTH_NAMES_FR: tuple[str, ...] = (
    "Janvier", "Février", "Mars", "Avril", "Mai", "Juin",
    "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre",
)
WEEKDAY_NAMES_FR: tuple[str, ...] = ("Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim")


@dataclass(slots=True)
class DayCell:
    """Une journée du calendrier et les interventions qui s'y rattachent."""

    day_date: date
    in_month: bool
    interventions: list[Intervention] = field(default_factory=list)

    @property
    def count(self) -> int:
        """Nombre d'interventions sur la journée."""
        return len(self.interventions)

    @property
    def dominant_color(self) -> str | None:
        """Couleur dominante de la journée (statut le plus prioritaire)."""
        if not self.interventions:
            return None
        priority = [
            StatutIntervention.EN_COURS,
            StatutIntervention.A_FAIRE,
            StatutIntervention.PLANIFIEE,
            StatutIntervention.TERMINEE,
            StatutIntervention.ANNULEE,
        ]
        statuts = {iv.statut for iv in self.interventions}
        for statut in priority:
            if statut in statuts:
                return STATUT_COLORS[statut]
        return STATUT_COLORS[StatutIntervention.A_FAIRE]


class CalendarModel:
    """Construit la matrice mensuelle et y répartit les interventions."""

    def __init__(self, first_weekday: int = 0) -> None:
        """Initialise le modèle.

        Args:
            first_weekday: Premier jour de la semaine (0 = lundi).
        """
        self._cal = calendar.Calendar(firstweekday=first_weekday)

    def build_month(
        self, year: int, month: int, interventions: list[Intervention]
    ) -> list[list[DayCell]]:
        """Construit la grille (semaines × 7 jours) d'un mois donné.

        Args:
            year: Année cible.
            month: Mois cible (1-12).
            interventions: Interventions à projeter sur le mois.

        Returns:
            Une liste de semaines, chacune contenant 7 :class:`DayCell`.
        """
        by_day = self._index_by_day(interventions)
        weeks: list[list[DayCell]] = []
        for week in self._cal.monthdatescalendar(year, month):
            cells: list[DayCell] = []
            for day in week:
                cells.append(
                    DayCell(
                        day_date=day,
                        in_month=(day.month == month),
                        interventions=by_day.get(day, []),
                    )
                )
            weeks.append(cells)
        return weeks

    @staticmethod
    def _index_by_day(
        interventions: list[Intervention],
    ) -> dict[date, list[Intervention]]:
        """Indexe les interventions par chaque journée couverte."""
        index: dict[date, list[Intervention]] = {}
        for iv in interventions:
            start = iv.date_debut
            end = iv.date_fin or iv.date_debut
            if start is None or end is None:
                continue
            if end < start:
                start, end = end, start
            current = start
            while current <= end:
                index.setdefault(current, []).append(iv)
                current = current.fromordinal(current.toordinal() + 1)
        return index

    @staticmethod
    def month_label(year: int, month: int) -> str:
        """Retourne un libellé lisible « Mois AAAA »."""
        return f"{MONTH_NAMES_FR[month - 1]} {year}"
