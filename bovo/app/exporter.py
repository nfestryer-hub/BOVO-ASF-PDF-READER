"""Export des interventions vers Excel, CSV, JSON et PDF.

Module métier séparé du GUI. L'export Excel s'appuie sur ``openpyxl`` et
l'export PDF sur PyMuPDF (fitz), déjà imposés par le projet.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, date, datetime
from pathlib import Path

import fitz  # PyMuPDF
from openpyxl import Workbook

from app.database import Database
from app.logger import LogAction, get_logger, log_action
from app.models import Intervention
from app.utils import format_date_fr

logger = get_logger("exporter")


def _compute_column_widths(
    headers: list[str], rows: list[list[str]], usable_w: float,
    *, min_w: float = 42.0, sample: int = 60,
) -> list[float]:
    """Calcule des largeurs de colonnes proportionnelles au contenu.

    Prend la longueur maximale (en caractères) observée dans chaque colonne
    (parmi l'en-tête et un échantillon des lignes) puis répartit ``usable_w``
    au prorata, en garantissant une largeur minimale par colonne.
    """
    n = max(len(headers), 1)
    max_chars = [max(len(h or ""), 8) for h in headers]
    for row in rows[:sample]:
        for idx in range(n):
            value = row[idx] if idx < len(row) else ""
            length = min(len(str(value or "")), 60)  # borne pour éviter les cas extrêmes.
            if length > max_chars[idx]:
                max_chars[idx] = length
    total = sum(max_chars)
    if total <= 0:
        return [usable_w / n] * n
    raw = [(m / total) * usable_w for m in max_chars]
    # Applique le plancher (min_w) puis normalise.
    widths = [max(min_w, w) for w in raw]
    scale = usable_w / sum(widths)
    return [w * scale for w in widths]

_COLUMNS: tuple[tuple[str, str], ...] = (
    ("ouvrage", "Ouvrage"),
    ("objet", "Objet"),
    ("autoroute", "Autoroute"),
    ("secteur", "Secteur"),
    ("pr_debut", "PR début"),
    ("pr_fin", "PR fin"),
    ("sens", "Sens"),
    ("longueur", "Longueur"),
    ("diametre", "Diamètre"),
    ("type_ouvrage", "Type d'ouvrage"),
    ("date_debut", "Date début"),
    ("date_fin", "Date fin"),
    ("statut", "Statut"),
    ("commentaire", "Commentaire"),
)


def _row_values(iv: Intervention) -> list[str]:
    """Sérialise une intervention en liste de chaînes pour export tabulaire."""
    values: list[str] = []
    for attr, _ in _COLUMNS:
        raw = getattr(iv, attr)
        if isinstance(raw, date):
            values.append(format_date_fr(raw))
        elif hasattr(raw, "value"):
            values.append(str(raw.value))
        else:
            values.append("" if raw is None else str(raw))
    return values


class Exporter:
    """Fournit les exports multi-formats des interventions."""

    def __init__(self, database: Database) -> None:
        self._db = database

    def to_excel(self, interventions: list[Intervention], destination: Path) -> Path:
        """Exporte les interventions au format Excel (.xlsx)."""
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Interventions"
        sheet.append([label for _, label in _COLUMNS])
        for iv in interventions:
            sheet.append(_row_values(iv))
        destination.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(str(destination))
        log_action(self._db, LogAction.EXPORT, f"Export Excel : {destination.name}")
        return destination

    def to_csv(self, interventions: list[Intervention], destination: Path) -> Path:
        """Exporte les interventions au format CSV (séparateur ';')."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle, delimiter=";")
            writer.writerow([label for _, label in _COLUMNS])
            for iv in interventions:
                writer.writerow(_row_values(iv))
        log_action(self._db, LogAction.EXPORT, f"Export CSV : {destination.name}")
        return destination

    def to_json(self, interventions: list[Intervention], destination: Path) -> Path:
        """Exporte les interventions au format JSON."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "exported_at": datetime.now(UTC).isoformat(),
            "count": len(interventions),
            "interventions": [iv.to_row() for iv in interventions],
        }
        destination.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log_action(self._db, LogAction.EXPORT, f"Export JSON : {destination.name}")
        return destination

    def to_pdf(self, interventions: list[Intervention], destination: Path) -> Path:
        """Exporte un planning lisible au format PDF via PyMuPDF."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open()
        page = document.new_page()
        margin, top = 40, 60
        page.insert_text(
            (margin, 40),
            f"Bovo ASF Manager — Export du {format_date_fr(date.today())}",
            fontsize=14,
        )
        line_height = 16
        y = top
        for iv in interventions:
            if y > page.rect.height - margin:
                page = document.new_page()
                y = top
            text = (
                f"{iv.ouvrage} | {iv.objet} | {iv.autoroute} | "
                f"{format_date_fr(iv.date_debut)}→{format_date_fr(iv.date_fin)} | "
                f"{iv.statut.value}"
            )
            page.insert_text((margin, y), text[:120], fontsize=9)
            y += line_height
        document.save(str(destination))
        document.close()
        log_action(self._db, LogAction.EXPORT, f"Export PDF : {destination.name}")
        return destination

    def table_to_pdf(
        self,
        title: str,
        headers: list[str],
        rows: list[list[str]],
        destination: Path,
    ) -> Path:
        """Exporte un tableau générique (mode tableur) au format PDF paysage.

        Le PDF est généré au format **A3 paysage** (1191 × 842 pt) pour offrir
        largement l'espace nécessaire aux modules ASF qui comportent jusqu'à
        13 colonnes. Les colonnes sont dimensionnées proportionnellement à la
        longueur du contenu et le texte est rendu via ``insert_textbox`` afin
        d'assurer un retour à la ligne automatique.

        Args:
            title: Titre imprimé en haut de la première page.
            headers: Libellés des colonnes.
            rows: Contenu du tableau (chaque ligne = liste alignée aux headers).
            destination: Chemin du PDF cible.

        Returns:
            Le chemin du PDF généré.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open()
        # A3 paysage — lisibilité maximale pour tables larges.
        page_width, page_height = 1191.0, 842.0
        margin_x, margin_y = 34.0, 48.0
        usable_w = page_width - 2 * margin_x

        n_cols = max(len(headers), 1)
        col_widths = _compute_column_widths(headers, rows, usable_w)

        header_font_size = 9
        cell_font_size = 8.5
        line_height = cell_font_size + 3

        def _content_lines(text: str, width: float) -> int:
            """Estime combien de lignes le texte occupera dans une cellule."""
            if not text:
                return 1
            char_w = cell_font_size * 0.52
            max_chars = max(int((width - 6) / char_w), 6)
            total = 1
            for chunk in text.replace("\r", "").split("\n"):
                total += max((len(chunk) - 1) // max_chars, 0)
            return max(total, 1)

        def _draw_cell(
            page: fitz.Page, x: float, y: float, w: float, h: float,
            text: str, *, header: bool,
        ) -> None:
            """Dessine une cellule (bordure + texte avec retour à la ligne)."""
            rect = fitz.Rect(x, y, x + w, y + h)
            if header:
                page.draw_rect(
                    rect, color=(0.1, 0.1, 0.1),
                    fill=(0.9, 0.23, 0.27), width=0.4,
                )
                fontsize, color = header_font_size, (1.0, 1.0, 1.0)
                fontname = "hebo"
            else:
                page.draw_rect(rect, color=(0.6, 0.6, 0.6), width=0.3)
                fontsize, color = cell_font_size, (0.05, 0.05, 0.05)
                fontname = "helv"
            text_rect = fitz.Rect(x + 3, y + 2, x + w - 2, y + h - 1)
            page.insert_textbox(
                text_rect, text or "", fontsize=fontsize, color=color,
                fontname=fontname, align=fitz.TEXT_ALIGN_LEFT,
            )

        def _new_page() -> tuple[fitz.Page, float]:
            page = document.new_page(width=page_width, height=page_height)
            page.insert_text(
                (margin_x, margin_y - 22),
                f"{title} — {format_date_fr(date.today())}",
                fontsize=14, color=(0.05, 0.05, 0.05), fontname="hebo",
            )
            # En-tête de tableau.
            x = margin_x
            header_h = header_font_size + 8
            for idx, label in enumerate(headers):
                _draw_cell(page, x, margin_y, col_widths[idx], header_h,
                           label, header=True)
                x += col_widths[idx]
            return page, margin_y + header_h

        page, y = _new_page()
        for row in rows:
            padded = list(row) + [""] * max(0, n_cols - len(row))
            row_lines = max(
                _content_lines(padded[i] or "", col_widths[i])
                for i in range(n_cols)
            )
            row_h = row_lines * line_height + 4
            if y + row_h > page_height - margin_y - 20:
                page, y = _new_page()
            x = margin_x
            for idx in range(n_cols):
                _draw_cell(page, x, y, col_widths[idx], row_h,
                           padded[idx] or "", header=False)
                x += col_widths[idx]
            y += row_h

        # Pied de page : nombre de lignes + auteur, sur la dernière page.
        page.insert_text(
            (margin_x, page_height - 20),
            f"{len(rows)} ligne(s) — Bovo ASF Manager · Développé par HENRI Dylan",
            fontsize=8, color=(0.4, 0.4, 0.4),
        )
        document.save(str(destination))
        document.close()
        log_action(
            self._db, LogAction.EXPORT,
            f"Export PDF (tableur) : {destination.name} — {len(rows)} ligne(s)",
        )
        return destination

    # ------------------------------------------------------------------ #
    # Export ASF : mise en page conforme au classeur "Form visites
    # assainissement V2026-06-01.xlsx" — chaque rapport = 1 ligne
    # subdivisée en 4 sections (Informations Générales, Caractéristiques,
    # Surveillance générale, Autres documents).
    # ------------------------------------------------------------------ #
    def asf_rapports_to_pdf(
        self,
        sections: list[tuple[str, list[tuple[str, str]]]],
        rapports: list[dict[str, str]],
        destination: Path,
    ) -> Path:
        """Exporte les rapports d'inspection au format ASF (mise en page Excel).

        Args:
            sections: Structure ``[(titre_section, [(col_db, libellé), ...])]``.
                Typiquement :data:`app.inspections.ASF_RAPPORT_SECTIONS`.
            rapports: Liste des rapports (chacun un dict ``col_db → valeur``).
            destination: Chemin du PDF cible.

        Returns:
            Le chemin du PDF généré.

        Le PDF est en A3 paysage. En-têtes de sections colorés :
        rouge / bleu / orange / vert. Chaque ligne de rapport = 1 bande
        horizontale sous les en-têtes fusionnés.
        """
        destination.parent.mkdir(parents=True, exist_ok=True)
        document = fitz.open()
        page_width, page_height = 1191.0, 842.0
        margin_x, margin_y = 30.0, 60.0
        usable_w = page_width - 2 * margin_x

        # Couleurs des sections (RGB [0..1]).
        section_colors: list[tuple[float, float, float]] = [
            (0.902, 0.224, 0.275),  # E63946 rouge ASF
            (0.271, 0.482, 0.616),  # 457B9D bleu
            (0.957, 0.635, 0.380),  # F4A261 orange
            (0.165, 0.616, 0.561),  # 2A9D8F vert
        ]

        # Largeur relative de chaque champ. Les champs "long" (commentaires,
        # description, lien Maps, photos) ont un poids double pour éviter la
        # troncature. Les champs très courts sont compacts.
        _LONG_FIELDS = {
            "description", "photo", "lien_maps", "type_defaut",
            "commentaire", "observations",
        }
        _COMPACT_FIELDS = {
            "sens", "urgence",
        }

        def _field_weight(col: str) -> float:
            if col in _LONG_FIELDS:
                return 2.4
            if col in _COMPACT_FIELDS:
                return 0.85
            return 1.2

        # Calcule les largeurs de section proportionnelles à la somme des
        # poids des champs qui les composent.
        section_weights = [
            sum(_field_weight(col) for col, _ in fields) or 1.0
            for _, fields in sections
        ]
        total_weight = sum(section_weights)
        section_widths = [(w / total_weight) * usable_w for w in section_weights]

        # Largeur de chaque colonne DANS une section.
        field_widths_by_section: list[list[float]] = []
        for (_title, fields), section_w, s_weight in zip(
            sections, section_widths, section_weights, strict=False,
        ):
            if not fields:
                field_widths_by_section.append([])
                continue
            field_widths_by_section.append([
                (_field_weight(col) / s_weight) * section_w
                for col, _ in fields
            ])

        header_row_h = 32.0
        subheader_row_h = 48.0
        min_data_row_h = 36.0
        title_size = 15
        section_size = 11
        subheader_size = 8.0
        cell_size = 8.5

        def _content_lines(text: str, width: float) -> int:
            if not text:
                return 1
            char_w = cell_size * 0.53
            max_chars = max(int((width - 6) / char_w), 6)
            total = 1
            for chunk in text.replace("\r", "").split("\n"):
                total += max((len(chunk) - 1) // max_chars, 0)
            return max(total, 1)

        def _draw_cell(
            page: "fitz.Page", x: float, y: float, w: float, h: float,
            text: str, *, fill: tuple[float, float, float] | None = None,
            text_color: tuple[float, float, float] = (0.05, 0.05, 0.05),
            fontsize: float = cell_size, fontname: str = "helv",
            align: int = fitz.TEXT_ALIGN_LEFT,
        ) -> None:
            rect = fitz.Rect(x, y, x + w, y + h)
            border_c = (0.55, 0.55, 0.55)
            if fill is not None:
                page.draw_rect(rect, color=border_c, fill=fill, width=0.5)
            else:
                page.draw_rect(rect, color=border_c, width=0.4)
            text_rect = fitz.Rect(x + 3, y + 2, x + w - 2, y + h - 1)
            page.insert_textbox(
                text_rect, text or "", fontsize=fontsize,
                color=text_color, fontname=fontname, align=align,
            )

        def _draw_page_header(page: "fitz.Page") -> float:
            """Trace le titre + les en-têtes de sections + les libellés colonnes."""
            page.insert_text(
                (margin_x, margin_y - 32),
                "Rapports d'inspection ASF — Bovo ASF Manager",
                fontsize=title_size, color=(0.05, 0.05, 0.05), fontname="hebo",
            )
            page.insert_text(
                (margin_x, margin_y - 14),
                f"Formulaire visites assainissement V2026-06-01 · "
                f"édité le {format_date_fr(date.today())}",
                fontsize=9, color=(0.35, 0.35, 0.35), fontname="helv",
            )

            # En-tête de sections colorés (ligne 1 fusionnée par section).
            x = margin_x
            for idx, ((title_txt, _fields), sw) in enumerate(
                zip(sections, section_widths, strict=False),
            ):
                _draw_cell(
                    page, x, margin_y, sw, header_row_h, title_txt,
                    fill=section_colors[idx % len(section_colors)],
                    text_color=(1.0, 1.0, 1.0),
                    fontsize=section_size, fontname="hebo",
                    align=fitz.TEXT_ALIGN_CENTER,
                )
                x += sw

            # Sous-en-têtes : libellé de chaque champ.
            y_sub = margin_y + header_row_h
            x = margin_x
            for idx, (_title, fields) in enumerate(sections):
                widths = field_widths_by_section[idx]
                for (_col, label), w in zip(fields, widths, strict=False):
                    _draw_cell(
                        page, x, y_sub, w, subheader_row_h, label,
                        fill=(0.95, 0.95, 0.97),
                        text_color=(0.1, 0.1, 0.1),
                        fontsize=subheader_size, fontname="hebo",
                        align=fitz.TEXT_ALIGN_CENTER,
                    )
                    x += w
            return y_sub + subheader_row_h

        def _new_page() -> tuple["fitz.Page", float]:
            new_page = document.new_page(width=page_width, height=page_height)
            data_y = _draw_page_header(new_page)
            return new_page, data_y

        page, y = _new_page()

        for rapport in rapports:
            # Calcule la hauteur totale de la ligne (max sur toutes les colonnes).
            row_lines_max = 1
            for idx, (_title, fields) in enumerate(sections):
                widths = field_widths_by_section[idx]
                for (col, _label), w in zip(fields, widths, strict=False):
                    val = str(rapport.get(col, "") or "")
                    lines_needed = _content_lines(val, w)
                    if lines_needed > row_lines_max:
                        row_lines_max = lines_needed
            row_h = max(min_data_row_h, row_lines_max * (cell_size + 2.5) + 8)

            # Nouvelle page si dépassement.
            if y + row_h > page_height - margin_y - 22:
                page, y = _new_page()

            # Dessine chaque cellule de la ligne.
            x = margin_x
            for idx, (_title, fields) in enumerate(sections):
                widths = field_widths_by_section[idx]
                for (col, _label), w in zip(fields, widths, strict=False):
                    val = str(rapport.get(col, "") or "")
                    # Formate la date pour lisibilité FR.
                    if col in ("date",) and val:
                        try:
                            val = format_date_fr(date.fromisoformat(val[:10])) or val
                        except ValueError:
                            pass
                    _draw_cell(page, x, y, w, row_h, val)
                    x += w
            y += row_h

        # Pied de page final.
        page.insert_text(
            (margin_x, page_height - 22),
            f"{len(rapports)} rapport(s) ASF — Bovo ASF Manager "
            "· Développé par HENRI Dylan",
            fontsize=8, color=(0.4, 0.4, 0.4),
        )

        document.save(str(destination))
        document.close()
        log_action(
            self._db, LogAction.EXPORT,
            f"Export ASF (rapports) : {destination.name} — {len(rapports)} rapport(s)",
        )
        return destination
