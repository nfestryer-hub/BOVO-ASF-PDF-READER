"""Parser du planning ASF format « Planning 2026.pdf ».

Ce format est différent du listing d'ouvrages BOVO historique : chaque
bloc commence par un en-tête d'autoroute (``A63``, ``A64``, ``A641``…),
suivi d'une plage de PR (``Pk 166,1 à 183,5``), puis d'un tableau ligne
par ligne :

    Identifiant | Sens/BDD | PR début | PR fin | Longueur | Type ouvrage + dates | Nb équipes | Nuit

Exemple ::

    21499 Sens 1 BDD
    183,038
    178,64
    4401 ml
    Caniveau à fente 12/10au 13/10 et 13/10 au 14/10
    2
    Oui

Chaque ligne peut ne pas avoir de Sens (l'ouvrage hérite alors du Sens
de la ligne précédente). Les dates peuvent être multiples (``12/10 au
13/10 et 13/10 au 14/10``) ou une plage (``du 30/11 au 02/12``).
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import fitz  # PyMuPDF

from app.parser_pdf import ParsedIntervention

# Motifs de détection
_RE_AUTOROUTE = re.compile(r"^A\d{2,4}$")
_RE_PK_RANGE = re.compile(r"^Pk\s+[\d,.]+\s+à\s+", re.IGNORECASE)
_RE_OUVRAGE_ID = re.compile(r"^(\d{4,6})(?:\s+(.+))?$")
_RE_PR_VALUE = re.compile(r"^\d{1,3}[,.]\d+$")
_RE_LONGUEUR = re.compile(r"^(\d+)\s*ml$", re.IGNORECASE)
_RE_INT = re.compile(r"^\d+$")
_RE_OUI_NON = re.compile(r"^(Oui|Non)$", re.IGNORECASE)

# Extraction des dates au format JJ/MM (année sous-entendue = 2026 par défaut).
_RE_DATE = re.compile(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?")


def _to_date(day: int, month: int, year_hint: int = 2026) -> date | None:
    """Convertit un triplet (j, m, aa) en :class:`date`. ``None`` si invalide."""
    try:
        y = year_hint
        return date(y, month, day)
    except ValueError:
        return None


def _extract_dates(chunk: str, year_hint: int = 2026) -> list[date]:
    """Extrait toutes les dates ``JJ/MM`` de ``chunk`` dans l'ordre."""
    dates: list[date] = []
    for match in _RE_DATE.finditer(chunk):
        day, month = int(match.group(1)), int(match.group(2))
        year_str = match.group(3)
        y = year_hint
        if year_str:
            y = int(year_str)
            if y < 100:
                y += 2000
        d = _to_date(day, month, y)
        if d is not None:
            dates.append(d)
    return dates


def parse_planning_pdf(pdf_path: Path) -> list[ParsedIntervention]:
    """Parse un PDF de planning ASF (format « Planning 2026 »).

    Retourne une liste de :class:`ParsedIntervention` prête à être
    intégrée par :class:`Planner` / :class:`RemotePlanner` (mêmes
    champs que le parser historique — assure la compatibilité avec le
    flux d'import et le dialogue de revue post-import).
    """
    doc = fitz.open(str(pdf_path))
    try:
        raw_text = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()

    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

    results: list[ParsedIntervention] = []
    current_autoroute = ""
    current_sens = ""
    year_hint = 2026

    i = 0
    while i < len(lines):
        ln = lines[i]
        # Nouveau bloc autoroute.
        if _RE_AUTOROUTE.match(ln):
            current_autoroute = ln
            current_sens = ""
            i += 1
            continue
        # Ligne d'année (« Date retenue en 2026 »).
        year_match = re.search(r"20\d{2}", ln)
        if "Date retenue" in ln and year_match:
            year_hint = int(year_match.group())
            i += 1
            continue
        # Ligne PR ou headers (Pk / Nombre / Nuit) : ignorée.
        if (_RE_PK_RANGE.match(ln)
                or ln.lower().startswith("nombre d'équipe")
                or ln.lower().startswith("nuit")
                or ln.lower() in {"pk", "prévoir", "l'entreprise"}):
            i += 1
            continue
        # Ligne "0" isolée (colonne Nuit vide en fin de bloc) : ignorée.
        if ln == "0":
            i += 1
            continue
        # Identifiant d'ouvrage : entier 4-6 chiffres éventuellement suivi
        # du sens ("21499 Sens 1 BDD").
        m = _RE_OUVRAGE_ID.match(ln)
        if not m or not current_autoroute:
            i += 1
            continue

        ouvrage_id, sens_inline = m.group(1), m.group(2)
        if sens_inline:
            current_sens = sens_inline.strip()

        # Consomme les lignes suivantes : PR debut, PR fin, longueur,
        # type ouvrage + dates, nb équipes, Oui/Non.
        pr_debut = ""
        pr_fin = ""
        longueur = ""
        type_ouvrage = ""
        dates_chunk = ""
        j = i + 1
        # PR début
        if j < len(lines) and _RE_PR_VALUE.match(lines[j]):
            pr_debut = lines[j].replace(",", ".")
            j += 1
        # PR fin
        if j < len(lines) and _RE_PR_VALUE.match(lines[j]):
            pr_fin = lines[j].replace(",", ".")
            j += 1
        # Longueur (« 4401 ml »)
        if j < len(lines):
            lm = _RE_LONGUEUR.match(lines[j])
            if lm:
                longueur = lm.group(1)
                j += 1
        # Type ouvrage + dates : ligne texte contenant des dates JJ/MM.
        if j < len(lines) and _RE_DATE.search(lines[j]):
            dates_chunk = lines[j]
            # Extraire le type (avant la première date).
            first_date_pos = _RE_DATE.search(dates_chunk).start()
            type_ouvrage = dates_chunk[:first_date_pos].strip()
            j += 1
        # Nb équipes (entier)
        if j < len(lines) and _RE_INT.match(lines[j]):
            j += 1  # valeur ignorée pour l'instant (non stockée)
        # Oui/Non (Nuit)
        nuit = ""
        if j < len(lines) and _RE_OUI_NON.match(lines[j]):
            nuit = lines[j].strip().capitalize()
            j += 1

        # Ne créer une intervention QUE si on a au moins un ID + une date.
        parsed_dates = _extract_dates(dates_chunk, year_hint) if dates_chunk else []
        if not parsed_dates:
            i = j
            continue

        objet_parts = [type_ouvrage]
        if nuit:
            objet_parts.append(f"({nuit})")
        objet = " ".join(p for p in objet_parts if p) or type_ouvrage

        results.append(ParsedIntervention(
            ouvrage=ouvrage_id,
            objet=objet,
            autoroute=current_autoroute,
            secteur="",
            pr_debut=pr_debut,
            pr_fin=pr_fin,
            sens=current_sens,
            longueur=longueur,
            diametre="",
            type_ouvrage=type_ouvrage,
            dates=parsed_dates,
            observations=f"Nuit: {nuit}" if nuit.lower() == "oui" else "",
            pdf_name=pdf_path.name,
            pdf_path=str(pdf_path),
        ))
        i = j

    return results


def is_planning_format(pdf_path: Path) -> bool:
    """Détecte si le PDF est au format « Planning ASF 2026 ».

    Heuristique : le texte contient une ligne matchant ``A\\d{2,4}$``,
    suivie d'une ligne ``Date retenue en 20\\d{2}``. C'est très
    discriminant vs le format historique « Listing_Ouvrages_BOVO ».
    """
    try:
        doc = fitz.open(str(pdf_path))
        text = doc[0].get_text() if doc.page_count else ""
        doc.close()
    except Exception:  # noqa: BLE001
        return False
    return bool(
        re.search(r"^A\d{2,4}$", text, re.MULTILINE)
        and re.search(r"Date retenue en 20\d{2}", text)
    )
