"""Adaptateurs REST qui exposent la même interface que les services locaux.

Objectif : permettre aux vues CustomTkinter de continuer à utiliser des
appels comme ``planner.search(...)`` ou ``inspections.list_rows(sheet)``
alors que la donnée provient désormais du backend FastAPI centralisé. Aucun
service n'ouvre plus la base SQLite pour l'authentification ou les données
métier — tout passe par :class:`app.api_client.ApiClient`.

Les seules sources de vérité locales conservées sont :

* ``Settings`` (préférences par poste : thème, URL serveur, remember me…) ;
* ``Journal`` (logs de session locale : ouverture PDF, exports…) ;
* Le parseur PDF (``PdfParser``) et l'import Excel — le fichier est lu
  localement puis chaque ligne extraite est envoyée à l'API.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.api_client import ApiClient, ApiError
from app.audit import AuditEntry
from app.calendar import CalendarModel
from app.documents import Document
from app.inspections import (
    FORM_FIELDS,
    ORDERED_COLUMNS,
    SHEET_LABELS,
    FieldSpec,
)
from app.logger import get_logger
from app.models import Intervention, StatutIntervention
from app.session import RemoteUser, Session
from app.utils import parse_iso_date

logger = get_logger("remote_services")


class AutoLoginNetworkError(RuntimeError):
    """L'auto-login a échoué à cause d'une erreur réseau/serveur transitoire.

    Signale à l'appelant qu'il ne faut PAS purger le refresh token
    persisté — l'utilisateur pourra retenter plus tard.
    """


# Mapping colonne → libellé, déduit du schéma FORM_FIELDS partagé.
COLUMN_LABELS: dict[str, str] = {
    field.column: field.label
    for fields in FORM_FIELDS.values()
    for field in fields
}

# Unités des KPIs ASF (utilisées pour l'affichage dashboard).
KPI_UNITS: dict[str, str] = {
    "ml_inspectes": "ml",
    "regards": "",
    "heures": "h",
    "ml_par_heure": "ml/h",
}


# --------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------- #
class RemoteAuthService:
    """Adaptateur REST qui remplace :class:`app.auth.AuthService`.

    L'interface est volontairement identique pour que les dialogs GUI
    existants (login, gestion des utilisateurs) fonctionnent sans
    modification. Toutes les opérations vont taper l'API FastAPI ;
    aucune requête SQLite n'est faite ici.
    """

    def __init__(self, client: ApiClient, session: Session) -> None:
        self._client = client
        self._session = session

    # ------------------------------------------------------------------ #
    # Session
    # ------------------------------------------------------------------ #
    @property
    def session(self) -> Session:
        """Retourne la session courante (compat interface AuthService)."""
        return self._session

    @property
    def current_user(self) -> RemoteUser | None:
        """Utilisateur courant, ``None`` si non connecté."""
        return self._session.user

    # ------------------------------------------------------------------ #
    # Login / logout
    # ------------------------------------------------------------------ #
    def login(self, username: str, password: str) -> RemoteUser | None:
        """Authentifie via ``POST /api/auth/login`` et lie la session."""
        try:
            user_data = self._client.login(username, password)
        except ApiError:
            return None
        return self._session.bind(user_data)

    def logout(self) -> None:
        """Termine la session côté client (JWT stateless — aucune requête)."""
        self._session.clear()

    def try_auto_login(self, refresh_token: str) -> RemoteUser | None:
        """Reconnexion silencieuse à partir d'un refresh token persisté.

        Utilise ``POST /api/auth/refresh`` pour obtenir un nouvel access
        token, puis ``GET /api/auth/me`` pour récupérer l'utilisateur.

        Retourne ``None`` si :
          * le token est expiré / invalide (HTTP 401/403) → l'appelant DOIT
            purger le refresh token persisté ;
          * le serveur est temporairement injoignable → l'appelant NE DOIT
            PAS purger le token (transient error).

        Lève :class:`AutoLoginNetworkError` sur erreur réseau/serveur pour
        que ``main._launch_login`` distingue les deux cas.
        """
        if not refresh_token:
            logger.info("try_auto_login: aucun refresh_token fourni.")
            return None
        self._client.set_tokens("", refresh_token)
        try:
            self._client.refresh_access_token()
            me = self._client.me()
        except ApiError as exc:
            # 401/403 = token révoqué/expiré → on purge côté appelant.
            if exc.status_code in (401, 403):
                logger.info(
                    "try_auto_login: refresh token invalide (HTTP %s) — purge.",
                    exc.status_code,
                )
                self._client.logout()
                return None
            # Autre code (500, 502…) : problème serveur, on conserve le token.
            logger.warning(
                "try_auto_login: erreur serveur HTTP %s — token conservé.",
                exc.status_code,
            )
            self._client.logout()
            raise AutoLoginNetworkError(str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 — timeout, ConnectionError…
            logger.warning(
                "try_auto_login: erreur réseau (%s) — token conservé.", exc,
            )
            self._client.logout()
            raise AutoLoginNetworkError(str(exc)) from exc
        logger.info("try_auto_login: succès (user=%s).", me.get("username"))
        return self._session.bind(me)

    # ------------------------------------------------------------------ #
    # Administration
    # ------------------------------------------------------------------ #
    def list_users(self) -> list[RemoteUser]:
        """Liste tous les utilisateurs (Admin uniquement côté serveur)."""
        return [RemoteUser.from_dict(u) for u in self._client.list_users()]

    def create_user(
        self, username: str, password: str, role: Any, full_name: str = "",
    ) -> RemoteUser:
        """Crée un utilisateur (Admin uniquement).

        Args:
            role: :class:`app.auth.Role` local (``.value`` extrait) OU chaîne.
        """
        role_value = getattr(role, "value", None) or str(role)
        data = self._client.create_user(username, password, role_value, full_name)
        return RemoteUser.from_dict(data)

    def change_password(self, user_id: int, new_password: str) -> None:
        """Modifie le mot de passe d'un utilisateur (soi-même ou Admin)."""
        self._client.change_password(user_id, new_password)

    def delete_user(self, user_id: int) -> None:
        """Supprime un utilisateur (Admin, sauf soi-même)."""
        current = self._session.user
        if current is not None and current.id == user_id:
            raise ValueError("Vous ne pouvez pas supprimer votre propre compte.")
        self._client.delete_user(user_id)


# --------------------------------------------------------------------- #
# Interventions (adaptateur du Planner)
# --------------------------------------------------------------------- #
@dataclass
class ImportResult:
    """Mirror complet de :class:`app.planner.ImportResult` (compat GUI)."""

    files_processed: int = 0
    interventions_created: int = 0
    interventions_updated: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def total_interventions(self) -> int:
        return self.interventions_created + self.interventions_updated


def _intervention_from_api(data: dict[str, Any]) -> Intervention:
    """Convertit un JSON API en :class:`Intervention` locale.

    Les dates absentes sont conservées à ``None`` (contrairement à un
    ``date.today()`` implicite qui masquerait le fait que l'intervention
    n'est pas encore planifiée).
    """
    return Intervention(
        id=data.get("id"),
        ouvrage=data.get("ouvrage", ""),
        objet=data.get("objet", ""),
        autoroute=data.get("autoroute", ""),
        secteur=data.get("secteur", ""),
        pr_debut=data.get("pr_debut", ""),
        pr_fin=data.get("pr_fin", ""),
        sens=data.get("sens", ""),
        longueur=data.get("longueur", ""),
        diametre=data.get("diametre", ""),
        type_ouvrage=data.get("type_ouvrage", ""),
        date_debut=parse_iso_date(data.get("date_debut") or ""),
        date_fin=parse_iso_date(data.get("date_fin") or ""),
        statut=StatutIntervention.from_value(data.get("statut", "À planifier")),
        pdf_path=data.get("pdf_path", ""),
        commentaire=data.get("commentaire", ""),
    )


class RemotePlanner:
    """Adaptateur REST du Planner local. Expose les mêmes signatures."""

    def __init__(self, client: ApiClient) -> None:
        self._client = client
        self._calendar = CalendarModel()

    # ------------------------------------------------------------------ #
    # Lecture
    # ------------------------------------------------------------------ #
    def _fetch_all(self, **filters: str) -> list[Intervention]:
        rows = self._client.list_interventions(**filters)
        return [_intervention_from_api(r) for r in rows]

    def search(
        self, *, search: str = "", statut: str = "", autoroute: str = "",
        secteur: str = "", ouvrage: str = "", query: str = "", **_: Any,
    ) -> list[Intervention]:
        """Recherche filtrée d'interventions (compat Planner.search).

        Accepte les mêmes kwargs que ``Planner.search`` (``search``,
        ``statut``, ``autoroute``, ``secteur``) + alias legacy ``query`` /
        ``ouvrage`` pour rétro-compatibilité.
        """
        api_filters: dict[str, str] = {}
        if autoroute and autoroute not in ("Toutes", ""):
            api_filters["autoroute"] = autoroute
        if statut and statut not in ("Tous", ""):
            api_filters["statut"] = statut
        needle = search or query or ouvrage
        if needle:
            api_filters["search"] = needle
        results = self._fetch_all(**api_filters)
        # Filtrage secteur côté client (le backend ne l'expose pas encore).
        if secteur:
            results = [iv for iv in results if iv.secteur == secteur]
        return results

    def get_statistics(self) -> dict[str, Any]:
        """Statistiques agrégées côté client — clés identiques à Planner.

        Retourne : ``total``, ``terminees``, ``a_faire``, ``pdfs``,
        ``autoroutes``, ``secteurs``, ``derniere_maj``, ``db_ok``.
        """
        interventions = self._fetch_all()
        seen_autoroutes: set[str] = set()
        seen_secteurs: set[str] = set()
        seen_pdfs: set[str] = set()
        terminees = 0
        a_faire = 0
        derniere_maj = ""
        for iv in interventions:
            if iv.pdf_path:
                seen_pdfs.add(iv.pdf_path)
            if iv.statut is StatutIntervention.TERMINEE:
                terminees += 1
            else:
                a_faire += 1
            if iv.autoroute:
                seen_autoroutes.add(iv.autoroute)
            if iv.secteur:
                seen_secteurs.add(iv.secteur)
            if iv.updated_at and iv.updated_at > derniere_maj:
                derniere_maj = iv.updated_at
        return {
            "total": len(interventions),
            "terminees": terminees,
            "a_faire": a_faire,
            "pdfs": len(seen_pdfs),
            "autoroutes": len(seen_autoroutes),
            "secteurs": len(seen_secteurs),
            "derniere_maj": derniere_maj or "—",
            "db_ok": True,
        }

    def filter_options(self) -> dict[str, list[str]]:
        """Retourne autoroutes / secteurs / statuts (clés identiques Planner)."""
        interventions = self._fetch_all()
        return {
            "autoroutes": sorted({iv.autoroute for iv in interventions if iv.autoroute}),
            "secteurs": sorted({iv.secteur for iv in interventions if iv.secteur}),
            "statuts": [s.value for s in StatutIntervention],
        }

    def build_calendar(self, year: int, month: int) -> list[Any]:
        """Construit la grille du calendrier pour un mois (mirror Planner)."""
        interventions = self._fetch_all()
        return self._calendar.build_month(year, month, interventions)

    def list_between(self, start: str | date, end: str | date) -> list[Intervention]:
        """Interventions actives sur une plage (ISO ou date).

        Signature miroir de :meth:`Database.list_interventions_between` :
        l'appelant passe deux dates ISO (``YYYY-MM-DD``) ou ``date``.
        """
        def _as_date(v: str | date) -> date | None:
            if isinstance(v, date):
                return v
            return parse_iso_date(v)

        start_d = _as_date(start)
        end_d = _as_date(end)
        if start_d is None or end_d is None:
            return []
        results: list[Intervention] = []
        for iv in self._fetch_all():
            if iv.date_debut is None:
                continue
            fin = iv.date_fin or iv.date_debut
            if iv.date_debut <= end_d and fin >= start_d:
                results.append(iv)
        return results

    def get(self, intervention_id: int) -> Intervention | None:
        """Retourne une intervention par id."""
        try:
            data = self._client._request(
                "GET", f"/api/interventions/{intervention_id}",
            )
        except ApiError:
            return None
        return _intervention_from_api(data)

    # ------------------------------------------------------------------ #
    # Écriture
    # ------------------------------------------------------------------ #
    def set_statut(self, intervention_id: int, statut: StatutIntervention) -> None:
        """Change le statut d'une intervention."""
        self._client.update_intervention(intervention_id, {"statut": statut.value})

    def delete(self, intervention_id: int) -> None:
        """Supprime une intervention."""
        self._client.delete_intervention(intervention_id)

    def upsert(self, intervention: Intervention) -> Intervention:
        """Crée ou met à jour une intervention (à partir du parseur PDF).

        Le backend upsert par ``ouvrage`` : si l'ouvrage existe déjà, la
        route ``POST /api/interventions`` met à jour la ligne existante.
        """
        payload = {
            "ouvrage": intervention.ouvrage, "objet": intervention.objet,
            "autoroute": intervention.autoroute, "secteur": intervention.secteur,
            "pr_debut": intervention.pr_debut, "pr_fin": intervention.pr_fin,
            "sens": intervention.sens,
            "longueur": intervention.longueur, "diametre": intervention.diametre,
            "type_ouvrage": intervention.type_ouvrage,
            "date_debut": intervention.date_debut.isoformat() if intervention.date_debut else "",
            "date_fin": intervention.date_fin.isoformat() if intervention.date_fin else "",
            "statut": intervention.statut.value,
            "pdf_path": intervention.pdf_path,
            "commentaire": intervention.commentaire,
        }
        data = self._client.create_intervention(payload)
        return _intervention_from_api(data)

    def import_pdfs(
        self, paths: list[Path],
        progress: Any | None = None,
    ) -> ImportResult:
        """Parse les PDF localement puis pousse chaque intervention via l'API.

        Renvoie un :class:`ImportResult` (mirror de :class:`app.planner.ImportResult`)
        avec ``files_processed`` / ``interventions_created`` / ``interventions_updated``
        et ``errors: list[str]``.
        """
        from app.parser_pdf import PdfParser  # import local (dép. lourde)
        parser = PdfParser()
        result = ImportResult()
        # Pré-charge la liste des ouvrages connus pour distinguer create/update.
        try:
            existing_ouvrages = {iv.ouvrage for iv in self._fetch_all()}
        except ApiError:
            existing_ouvrages = set()
        for idx, path in enumerate(paths, start=1):
            if progress is not None:
                try:
                    progress(idx, len(paths), f"Analyse de {path.name}")
                except Exception:  # noqa: BLE001 - callback GUI non critique
                    pass
            try:
                items = parser.parse_file(path)
            except Exception as exc:  # noqa: BLE001 — surface le message.
                logger.exception("Échec parsing %s", path.name)
                result.errors.append(f"Échec import {path.name} : {exc}")
                continue
            result.files_processed += 1
            if not items:
                result.errors.append(
                    f"⚠️ {path.name} : aucune intervention détectée dans le PDF."
                )
            if progress is not None:
                try:
                    progress(
                        idx, len(paths),
                        f"{path.name} → {len(items)} intervention(s) détectée(s)"
                    )
                except Exception:  # noqa: BLE001
                    pass
            for parsed in items:
                iv = _parsed_to_intervention(parsed, path)
                is_update = iv.ouvrage in existing_ouvrages
                try:
                    self.upsert(iv)
                    if is_update:
                        result.interventions_updated += 1
                    else:
                        result.interventions_created += 1
                        existing_ouvrages.add(iv.ouvrage)
                except ApiError as exc:
                    logger.warning(
                        "Échec upsert %s (%s): %s",
                        iv.ouvrage, path.name, exc.detail,
                    )
                    result.errors.append(
                        f"Échec {iv.ouvrage} ({path.name}) : {exc.detail}",
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Erreur inattendue lors de l'upsert")
                    result.errors.append(
                        f"Erreur {iv.ouvrage} ({path.name}) : {exc}",
                    )
        return result


def _parsed_to_intervention(parsed: Any, path: Path) -> Intervention:
    """Convertit un :class:`ParsedIntervention` en :class:`Intervention`.

    Mirror de :meth:`Planner._to_intervention` — évite l'import direct de
    ``Planner`` (qui traînerait la dépendance SQLite).
    """
    statut = (
        StatutIntervention.PLANIFIEE
        if getattr(parsed, "dates", None)
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
        pdf_path=str(path),
        commentaire=getattr(parsed, "observations", "") or "",
    )


# --------------------------------------------------------------------- #
# Modules ASF (inspections/rapports/incidents/matériel)
# --------------------------------------------------------------------- #
class RemoteInspectionService:
    """Adaptateur REST du ``InspectionService`` local.

    Toutes les lectures/écritures passent par ``/api/modules/{sheet}``. Les
    constantes de schéma (colonnes, formulaires) restent locales car elles
    sont partagées entre client et serveur.
    """

    SHEETS: tuple[str, ...] = ("inspections", "rapports", "incidents", "materiel")

    RAPPORT_PREFILL_MAP: dict[str, str] = {
        "date": "date",
        "n_inspection": "n_inspection",
        "autoroute": "autoroute",
        "secteur": "secteur",
        "inspecteur": "operateur",
    }

    def __init__(self, client: ApiClient) -> None:
        self._client = client
        # Référentiel des listes déroulantes — fetch lazy + cache local.
        self._referentiel_cache: dict[str, list[str]] | None = None

    def referentiel(self, ref_key: str) -> list[str]:
        """Retourne la liste de référence associée à une clé (compat local)."""
        if self._referentiel_cache is None:
            from app.inspections import DEFAULT_REFERENTIEL  # noqa: PLC0415
            self._referentiel_cache = dict(DEFAULT_REFERENTIEL)
        return self._referentiel_cache.get(ref_key, [])

    # ------------------------------------------------------------------ #
    # Métadonnées (côté client — schémas partagés)
    # ------------------------------------------------------------------ #
    @staticmethod
    def sheet_label(sheet: str) -> str:
        """Libellé humain d'un module."""
        return SHEET_LABELS.get(sheet, sheet)

    @staticmethod
    def list_columns(sheet: str) -> list[tuple[str, str]]:
        """Retourne les paires (colonne, libellé) pour l'affichage table."""
        return [(col, COLUMN_LABELS.get(col, col)) for col in ORDERED_COLUMNS[sheet]]

    @staticmethod
    def form_fields(sheet: str) -> list[FieldSpec]:
        """Retourne la définition des champs pour le formulaire d'édition."""
        return FORM_FIELDS[sheet]

    # ------------------------------------------------------------------ #
    # CRUD
    # ------------------------------------------------------------------ #
    def list_rows(self, sheet: str, search: str = "") -> list[dict[str, str]]:
        """Liste les lignes d'un module (JSONB serveur → dicts plats client)."""
        rows = self._client.list_module(sheet, search=search)
        return [self._flatten(r) for r in rows]

    def get_row(self, sheet: str, row_id: int) -> dict[str, str] | None:
        """Retourne une ligne unique."""
        for row in self.list_rows(sheet):
            if int(row.get("id", 0)) == row_id:
                return row
        return None

    def save_row(
        self, sheet: str, data: dict[str, str], row_id: int | None = None,
    ) -> int:
        """Crée ou met à jour une ligne. Retourne l'id."""
        # On retire les clés vides pour rester lisible côté serveur.
        clean = {k: v for k, v in data.items() if v not in ("", None)}
        if row_id is None:
            created = self._client.create_module_row(sheet, clean)
            return int(created["id"])
        self._client.update_module_row(sheet, row_id, clean)
        return row_id

    def delete_row(self, sheet: str, row_id: int) -> None:
        """Supprime une ligne."""
        self._client.delete_module_row(sheet, row_id)

    # ------------------------------------------------------------------ #
    # Pré-remplissage rapport
    # ------------------------------------------------------------------ #
    def latest_inspection(self) -> dict[str, str] | None:
        """Renvoie la dernière inspection ajoutée (order desc côté serveur)."""
        rows = self.list_rows("inspections")
        return rows[0] if rows else None

    def prefill_rapport(self) -> dict[str, str]:
        """Retourne les valeurs pré-remplies pour un nouveau rapport."""
        prefill: dict[str, str] = {"prestataire": "BOVO & FILS"}
        inspection = self.latest_inspection()
        if inspection is None:
            return prefill
        for rapport_col, inspection_col in self.RAPPORT_PREFILL_MAP.items():
            value = (inspection.get(inspection_col) or "").strip()
            if value:
                prefill[rapport_col] = value
        return prefill

    # ------------------------------------------------------------------ #
    # KPIs + Export PDF (agrégation client)
    # ------------------------------------------------------------------ #
    def kpis(self) -> dict[str, str]:
        """KPIs ASF calculés à partir des inspections et rapports côté client.

        Clés identiques à ``InspectionService.kpis()`` pour compat GUI :
        ``ml_inspectes``, ``nb_inspections``, ``regards``, ``heures``,
        ``ml_h``.
        """
        rows = self.list_rows("inspections")
        ml_total = 0.0
        heures = 0.0
        for row in rows:
            try:
                ml_total += float((row.get("ml_inspectes") or "0").replace(",", "."))
            except ValueError:
                pass
            try:
                heures += float((row.get("heures_totales") or "0").replace(",", "."))
            except ValueError:
                pass
        rapports = self.list_rows("rapports")
        regards = sum(1 for _ in rapports)
        return {
            "ml_inspectes": f"{ml_total:.0f}",
            "nb_inspections": str(len(rows)),
            "regards": str(regards),
            "heures": f"{heures:.1f}",
            "ml_h": f"{(ml_total / heures) if heures else 0:.1f}",
        }

    @staticmethod
    def kpi_unit(key: str) -> str:
        """Unité d'un KPI (côté constantes partagées)."""
        return KPI_UNITS.get(key, "")

    def export_pdf(self, sheet: str, destination: Path) -> Path:
        """Génère un PDF tableur à partir des données API + Exporter local."""
        from app.exporter import Exporter  # import local
        rows = self.list_rows(sheet)
        columns = ORDERED_COLUMNS[sheet]
        labels = {f.column: f.label for f in FORM_FIELDS[sheet]}
        headers = [labels.get(c, c) for c in columns]
        data_rows = [[(row.get(c) or "") for c in columns] for row in rows]
        exporter = Exporter(database=None)  # DB non requise pour le tableur
        title = f"Bovo ASF Manager — {SHEET_LABELS[sheet]}"
        return exporter.table_to_pdf(title, headers, data_rows, destination)

    def import_workbook(self, path: Path) -> dict[str, int]:
        """Import Excel local → push chaque ligne via l'API.

        Utilise ponctuellement un ``InspectionService`` local (SQLite en
        mémoire éphémère) pour réutiliser le parseur Excel existant, puis
        recharge chaque ligne via l'API pour synchroniser tous les postes.
        """
        import sqlite3
        import tempfile

        from app.database import Database
        from app.inspections import InspectionService

        summary: dict[str, int] = {sheet: 0 for sheet in self.SHEETS}
        summary["interventions_liees"] = 0  # mirror InspectionService (non utilisé côté REST)
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            tmp_path = Path(tmp.name)
        try:
            local_db = Database(tmp_path)
            local_svc = InspectionService(local_db)
            local_svc.import_workbook(path)
            for sheet in self.SHEETS:
                for row in local_db.list_generic(sheet):
                    data = {k: v for k, v in row.items()
                            if k not in ("id", "created_at", "updated_at")}
                    try:
                        self.save_row(sheet, data)
                        summary[sheet] += 1
                    except ApiError:
                        continue
            local_db.close()
        finally:
            try:
                tmp_path.unlink()
            except (OSError, sqlite3.Error):
                pass
        return summary

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _flatten(row: dict[str, Any]) -> dict[str, str]:
        """Aplati une ligne API (``{id, sheet, data: {...}}``) en dict plat."""
        data = dict(row.get("data") or {})
        data["id"] = str(row.get("id", ""))
        return data


# --------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------- #
class RemoteDocumentService:
    """Adaptateur REST du DocumentService local."""

    def __init__(self, client: ApiClient) -> None:
        self._client = client

    @staticmethod
    def _to_document(row: dict[str, Any]) -> Document:
        """Convertit un payload API en dataclass Document."""
        uploaded_at = row.get("uploaded_at") or ""
        if isinstance(uploaded_at, datetime):
            uploaded_at = uploaded_at.isoformat()
        return Document(
            id=int(row.get("id", 0)),
            entity=row.get("entity", ""),
            entity_id=row.get("entity_id", ""),
            filename=row.get("filename", ""),
            storage_path="",  # non exposé — download via API
            mime_type=row.get("mime_type", ""),
            size_bytes=int(row.get("size_bytes") or 0),
            uploaded_by=row.get("uploaded_by", ""),
            uploaded_at=str(uploaded_at),
            notes=row.get("notes", ""),
        )

    def list_all(self, search: str = "") -> list[Document]:
        """Liste tous les documents (filtre client-side sur le texte)."""
        rows = self._client.list_documents()
        docs = [self._to_document(r) for r in rows]
        if search:
            needle = search.lower()
            docs = [d for d in docs if needle in d.filename.lower()
                    or needle in d.notes.lower()]
        return docs

    def list_for(self, entity: str, entity_id: str = "") -> list[Document]:
        """Documents attachés à une entité précise."""
        rows = self._client.list_documents(entity=entity, entity_id=entity_id)
        return [self._to_document(r) for r in rows]

    def attach(
        self, *, entity: str, entity_id: str, source: Path,
        uploaded_by: str = "", notes: str = "",
    ) -> Document:
        """Upload un fichier et l'attache à une entité."""
        data = self._client.upload_document(entity, entity_id, source, notes)
        return self._to_document(data)

    def delete(self, document_id: int) -> bool:
        """Supprime un document (base + fichier côté serveur)."""
        try:
            self._client.delete_document(document_id)
        except ApiError:
            return False
        return True

    def download(self, document: Document, destination: Path) -> Path:
        """Télécharge le fichier localement pour ouverture native."""
        return self._client.download_document(document.id, destination)


# --------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------- #
class RemoteAuditService:
    """Adaptateur REST du service d'audit local.

    L'API journalise automatiquement chaque écriture métier. Le GUI n'a
    plus besoin d'appeler ``record()`` — c'est un no-op ici.
    """

    def __init__(self, client: ApiClient) -> None:
        self._client = client

    def bind_session(self, username: str, role: str) -> None:
        """No-op : le serveur connaît déjà l'auteur via le JWT."""

    def record(self, **_: Any) -> None:
        """No-op : la journalisation est effectuée automatiquement côté API."""

    def list_entries(
        self, limit: int = 300, entity: str = "", search: str = "",
    ) -> list[AuditEntry]:
        """Retourne les dernières entrées d'audit."""
        rows = self._client.list_audit(entity=entity, search=search, limit=limit)
        return [AuditEntry.from_row({
            "id": row["id"],
            "username": row.get("username", ""),
            "role": row.get("role", ""),
            "action": row.get("action", ""),
            "entity": row.get("entity", ""),
            "entity_id": row.get("entity_id", ""),
            "before_json": _dump_json(row.get("before")),
            "after_json": _dump_json(row.get("after")),
            "created_at": str(row.get("created_at") or ""),
        }) for row in rows]


def _dump_json(value: Any) -> str:
    """Sérialise un dict JSON compatible avec :class:`AuditEntry.from_row`."""
    import json
    if isinstance(value, str):
        return value
    return json.dumps(value or {}, ensure_ascii=False, default=str)
