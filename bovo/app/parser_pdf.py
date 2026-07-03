"""Analyse des PDF de listing d'ouvrages ASF avec PyMuPDF (fitz).

Deux responsabilités distinctes :
    * :class:`DateParser` — conversion des chaînes de planification BOVO en
      véritables objets :class:`datetime.date` (gère les formats multiples).
    * :class:`PdfParser` — extraction tabulaire des interventions depuis un PDF.

Aucune écriture en base ici : le parser ne fait que produire des
:class:`~app.models.ParsedIntervention`.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import fitz  # PyMuPDF

from app.logger import get_logger
from app.models import ParsedIntervention
from app.utils import normalize_text

logger = get_logger("parser")

# Date finale d'un groupe : JJ/MM/AAAA (le séparateur peut être / ou -).
_ANCHOR_RE = re.compile(r"(\d{1,2})\s*[/-]\s*(\d{1,2})\s*[/-]\s*(\d{4})")
# Mots indiquant une plage continue de jours (« 23 au 26 »).
_RANGE_RE = re.compile(r"\bau\b|\bà\b|\bjusqu", re.IGNORECASE)


class DateParser:
    """Convertit les libellés de planification en dates Python.

    Formats reconnus (liste non exhaustive)::

        15/06/2026
        15 et 16/07/2026
        23 au 26/11/2026
        27-28-29-30/07/2026
        29-30/06/2026
        nuits 22 et 23/06/2026
        01 et 02/09/2026
    """

    def parse(self, raw: str) -> list[date]:
        """Retourne la liste triée et dédoublonnée des dates d'un libellé."""
        if not raw:
            return []
        text = raw.replace("\n", " ").strip().lower()
        results: set[date] = set()
        cursor = 0
        for match in _ANCHOR_RE.finditer(text):
            anchor_day, month, year = (int(g) for g in match.groups())
            segment = text[cursor:match.start()]
            cursor = match.end()
            days = [int(tok) for tok in re.findall(r"\d{1,2}", segment)]
            days.append(anchor_day)
            if _RANGE_RE.search(segment) and len(days) >= 2:
                day_values: list[int] = list(range(min(days), max(days) + 1))
            else:
                day_values = days
            for day in day_values:
                built = self._safe_date(year, month, day)
                if built is not None:
                    results.add(built)
        return sorted(results)

    @staticmethod
    def _safe_date(year: int, month: int, day: int) -> date | None:
        """Construit une date en ignorant silencieusement les valeurs invalides."""
        try:
            return date(year, month, day)
        except ValueError:
            return None


class PdfParser:
    """Extrait les interventions d'un PDF de listing d'ouvrages BOVO."""

    # Mappage des en-têtes (normalisés) vers les champs du modèle.
    _HEADER_MAP: dict[str, str] = {
        "objet": "objet",
        "identifiant": "ouvrage",
        "autoro": "autoroute",
        "autoroute": "autoroute",
        "autor": "autoroute",
        "secteur": "secteur",
        "pr debut": "pr_debut",
        "pr fin": "pr_fin",
        "sens": "sens",
        "longueur (m)": "longueur",
        "longueur": "longueur",
        "diametre": "diametre",
        "type d'ouvrage": "type_ouvrage",
        "type douvrage": "type_ouvrage",
        "planification": "_planification",
        "observations": "observations",
        "observation": "observations",
    }

    def __init__(self) -> None:
        self._dates = DateParser()

    def parse_file(self, pdf_path: Path) -> list[ParsedIntervention]:
        """Analyse un PDF et retourne la liste des interventions extraites.

        Args:
            pdf_path: Chemin du fichier PDF.

        Returns:
            Liste de :class:`ParsedIntervention`.

        Raises:
            FileNotFoundError: Si le fichier n'existe pas.
            RuntimeError: Si le PDF ne peut pas être ouvert par PyMuPDF.
        """
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF introuvable : {pdf_path}")
        try:
            document = fitz.open(str(pdf_path))
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"Impossible d'ouvrir le PDF : {exc}") from exc

        parsed: list[ParsedIntervention] = []
        try:
            for page in document:
                parsed.extend(self._parse_page(page, pdf_path))
        finally:
            document.close()

        logger.info("%s : %d intervention(s) extraite(s).", pdf_path.name, len(parsed))
        return parsed

    def _parse_page(self, page: fitz.Page, pdf_path: Path) -> list[ParsedIntervention]:
        """Analyse une page : tableaux d'abord, repli texte ensuite."""
        results: list[ParsedIntervention] = []
        tables = page.find_tables()
        for table in tables.tables:
            rows = table.extract()
            if len(rows) < 2:
                continue
            header_idx = self._build_header_index(rows[0])
            if "ouvrage" not in header_idx and "objet" not in header_idx:
                continue
            for row in rows[1:]:
                parsed = self._row_to_intervention(row, header_idx, pdf_path)
                if parsed is not None:
                    results.append(parsed)
        return results

    def _build_header_index(self, header_row: list[str | None]) -> dict[str, int]:
        """Associe chaque champ du modèle à son index de colonne."""
        index: dict[str, int] = {}
        for col, raw_name in enumerate(header_row):
            key = normalize_text(raw_name or "")
            field = self._HEADER_MAP.get(key)
            if field and field not in index:
                index[field] = col
        return index

    def _cell(self, row: list[str | None], index: dict[str, int], field: str) -> str:
        """Retourne la valeur texte nettoyée d'une cellule, ou chaîne vide."""
        col = index.get(field)
        if col is None or col >= len(row):
            return ""
        value = row[col]
        return ("" if value is None else str(value)).replace("\n", " ").strip()

    def _row_to_intervention(
        self,
        row: list[str | None],
        index: dict[str, int],
        pdf_path: Path,
    ) -> ParsedIntervention | None:
        """Transforme une ligne de tableau en :class:`ParsedIntervention`."""
        objet = self._cell(row, index, "objet")
        ouvrage = self._cell(row, index, "ouvrage")
        if not ouvrage:
            # Repli : numéro contenu dans l'objet, sinon objet + PR.
            embedded = re.search(r"\d{3,}", objet)
            ouvrage = embedded.group(0) if embedded else ""
        planning = self._cell(row, index, "_planification")
        dates = self._dates.parse(planning)

        if not ouvrage and not dates:
            return None  # Ligne vide ou de total : on l'ignore.

        if not ouvrage:
            ouvrage = f"{normalize_text(objet)}-{self._cell(row, index, 'pr_debut')}"

        return ParsedIntervention(
            ouvrage=ouvrage.strip(),
            objet=objet,
            autoroute=self._cell(row, index, "autoroute"),
            secteur=self._cell(row, index, "secteur"),
            pr_debut=self._cell(row, index, "pr_debut"),
            pr_fin=self._cell(row, index, "pr_fin"),
            sens=self._cell(row, index, "sens"),
            longueur=self._cell(row, index, "longueur"),
            diametre=self._cell(row, index, "diametre"),
            type_ouvrage=self._cell(row, index, "type_ouvrage"),
            dates=dates,
            observations=(
                self._cell(row, index, "observations")
                or (f"Planification : {planning}" if planning else "")
            ),
            pdf_name=pdf_path.name,
            pdf_path=str(pdf_path),
        )
