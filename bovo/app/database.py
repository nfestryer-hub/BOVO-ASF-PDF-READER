"""Couche de persistance SQLite de BOVO Planning Manager.

Encapsule toute la logique d'accès à la base ``database/bovo.db`` :
création des tables (``interventions``, ``pdf_files``, ``logs``, ``settings``),
opérations CRUD, détection de doublons par numéro d'ouvrage et statistiques.

La classe est sûre vis-à-vis des threads grâce à un verrou ré-entrant et à une
connexion ouverte avec ``check_same_thread=False``.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.logger import get_logger
from app.models import Intervention, LogEntry, PdfFile

logger = get_logger("database")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS interventions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ouvrage       TEXT NOT NULL,
    objet         TEXT DEFAULT '',
    autoroute     TEXT DEFAULT '',
    secteur       TEXT DEFAULT '',
    pr_debut      TEXT DEFAULT '',
    pr_fin        TEXT DEFAULT '',
    sens          TEXT DEFAULT '',
    longueur      TEXT DEFAULT '',
    diametre      TEXT DEFAULT '',
    type_ouvrage  TEXT DEFAULT '',
    date_debut    TEXT,
    date_fin      TEXT,
    statut        TEXT DEFAULT 'À faire',
    pdf_path      TEXT DEFAULT '',
    commentaire   TEXT DEFAULT '',
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(ouvrage)
);

CREATE TABLE IF NOT EXISTS pdf_files (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    name                TEXT NOT NULL,
    path                TEXT NOT NULL UNIQUE,
    interventions_count INTEGER DEFAULT 0,
    imported_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    action     TEXT NOT NULL,
    level      TEXT NOT NULL,
    message    TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interventions_ouvrage ON interventions(ouvrage);
CREATE INDEX IF NOT EXISTS idx_interventions_dates   ON interventions(date_debut, date_fin);
CREATE INDEX IF NOT EXISTS idx_interventions_statut  ON interventions(statut);
"""


class Database:
    """Gestionnaire de la base SQLite (singleton applicatif recommandé)."""

    def __init__(self, db_path: Path) -> None:
        """Initialise la connexion et crée le schéma si nécessaire.

        Args:
            db_path: Chemin du fichier de base de données SQLite.
        """
        self._path = db_path
        self._lock = threading.RLock()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._initialize_schema()
        logger.info("Base de données initialisée : %s", db_path)

    @property
    def path(self) -> Path:
        """Chemin du fichier de base."""
        return self._path

    def _initialize_schema(self) -> None:
        """Crée les tables et index si absents."""
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Interventions
    # ------------------------------------------------------------------ #
    def get_intervention_by_ouvrage(self, ouvrage: str) -> Intervention | None:
        """Retourne l'intervention associée à un numéro d'ouvrage, si elle existe."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM interventions WHERE ouvrage = ?", (ouvrage,)
            )
            row = cur.fetchone()
        return Intervention.from_row(dict(row)) if row else None

    def upsert_intervention(self, intervention: Intervention) -> tuple[Intervention, bool]:
        """Crée ou met à jour une intervention selon son numéro d'ouvrage.

        Returns:
            Un tuple ``(intervention, created)`` où ``created`` vaut ``True``
            si une nouvelle ligne a été insérée.
        """
        existing = self.get_intervention_by_ouvrage(intervention.ouvrage)
        now = datetime.now(UTC).isoformat()
        with self._lock:
            if existing is None:
                intervention.created_at = now
                intervention.updated_at = now
                row = intervention.to_row()
                row.pop("id", None)
                columns = ", ".join(row.keys())
                placeholders = ", ".join(["?"] * len(row))
                cur = self._conn.execute(
                    f"INSERT INTO interventions ({columns}) VALUES ({placeholders})",
                    tuple(row.values()),
                )
                self._conn.commit()
                intervention.id = cur.lastrowid
                return intervention, True

            intervention.id = existing.id
            intervention.created_at = existing.created_at
            intervention.updated_at = now
            row = intervention.to_row()
            row.pop("created_at", None)
            assignments = ", ".join(f"{k} = ?" for k in row if k != "id")
            values = [v for k, v in row.items() if k != "id"]
            values.append(intervention.id)
            self._conn.execute(
                f"UPDATE interventions SET {assignments} WHERE id = ?", values
            )
            self._conn.commit()
            return intervention, False

    def update_intervention_fields(self, intervention_id: int, **fields: Any) -> None:
        """Met à jour des champs ciblés d'une intervention."""
        if not fields:
            return
        fields["updated_at"] = datetime.now(UTC).isoformat()
        assignments = ", ".join(f"{k} = ?" for k in fields)
        with self._lock:
            self._conn.execute(
                f"UPDATE interventions SET {assignments} WHERE id = ?",
                (*fields.values(), intervention_id),
            )
            self._conn.commit()

    def delete_intervention(self, intervention_id: int) -> None:
        """Supprime une intervention par son identifiant."""
        with self._lock:
            self._conn.execute(
                "DELETE FROM interventions WHERE id = ?", (intervention_id,)
            )
            self._conn.commit()

    def list_interventions(
        self,
        *,
        search: str = "",
        statut: str = "",
        autoroute: str = "",
        secteur: str = "",
    ) -> list[Intervention]:
        """Retourne les interventions filtrées par critères optionnels."""
        query = "SELECT * FROM interventions WHERE 1=1"
        params: list[Any] = []
        if search:
            like = f"%{search}%"
            query += (
                " AND (ouvrage LIKE ? OR objet LIKE ? OR autoroute LIKE ?"
                " OR secteur LIKE ? OR type_ouvrage LIKE ? OR commentaire LIKE ?)"
            )
            params.extend([like] * 6)
        if statut:
            query += " AND statut = ?"
            params.append(statut)
        if autoroute:
            query += " AND autoroute = ?"
            params.append(autoroute)
        if secteur:
            query += " AND secteur = ?"
            params.append(secteur)
        query += " ORDER BY date_debut IS NULL, date_debut ASC, ouvrage ASC"
        with self._lock:
            cur = self._conn.execute(query, params)
            rows = cur.fetchall()
        return [Intervention.from_row(dict(r)) for r in rows]

    def list_interventions_between(self, start: str, end: str) -> list[Intervention]:
        """Retourne les interventions actives sur une plage de dates ISO."""
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT * FROM interventions
                WHERE date_debut IS NOT NULL
                  AND date(date_debut) <= date(?)
                  AND date(COALESCE(date_fin, date_debut)) >= date(?)
                ORDER BY date_debut ASC
                """,
                (end, start),
            )
            rows = cur.fetchall()
        return [Intervention.from_row(dict(r)) for r in rows]

    # ------------------------------------------------------------------ #
    # PDF
    # ------------------------------------------------------------------ #
    def upsert_pdf(self, pdf: PdfFile) -> PdfFile:
        """Enregistre ou met à jour les métadonnées d'un PDF importé."""
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO pdf_files (name, path, interventions_count, imported_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    name = excluded.name,
                    interventions_count = excluded.interventions_count,
                    imported_at = excluded.imported_at
                """,
                (pdf.name, pdf.path, pdf.interventions_count, pdf.imported_at),
            )
            self._conn.commit()
        return pdf

    def list_pdfs(self) -> list[PdfFile]:
        """Retourne tous les PDF importés (du plus récent au plus ancien)."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM pdf_files ORDER BY imported_at DESC"
            )
            rows = cur.fetchall()
        return [PdfFile.from_row(dict(r)) for r in rows]

    # ------------------------------------------------------------------ #
    # Logs
    # ------------------------------------------------------------------ #
    def add_log(self, *, action: str, level: str, message: str, created_at: str) -> None:
        """Insère une entrée dans le journal métier."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO logs (action, level, message, created_at) VALUES (?, ?, ?, ?)",
                (action, level, message, created_at),
            )
            self._conn.commit()

    def list_logs(self, limit: int = 200) -> list[LogEntry]:
        """Retourne les dernières entrées de journal."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM logs ORDER BY id DESC LIMIT ?", (limit,)
            )
            rows = cur.fetchall()
        return [LogEntry.from_row(dict(r)) for r in rows]

    # ------------------------------------------------------------------ #
    # Settings
    # ------------------------------------------------------------------ #
    def get_setting(self, key: str) -> str | None:
        """Retourne la valeur brute d'un paramètre, ou ``None``."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            )
            row = cur.fetchone()
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        """Définit ou met à jour un paramètre."""
        now = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                               updated_at = excluded.updated_at
                """,
                (key, value, now),
            )
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Statistiques
    # ------------------------------------------------------------------ #
    def statistics(self) -> dict[str, Any]:
        """Calcule les statistiques globales affichées au tableau de bord."""
        with self._lock:
            total = self._conn.execute(
                "SELECT COUNT(*) AS c FROM interventions"
            ).fetchone()["c"]
            done = self._conn.execute(
                "SELECT COUNT(*) AS c FROM interventions WHERE statut = 'Terminée'"
            ).fetchone()["c"]
            todo = self._conn.execute(
                "SELECT COUNT(*) AS c FROM interventions WHERE statut != 'Terminée'"
            ).fetchone()["c"]
            pdfs = self._conn.execute(
                "SELECT COUNT(*) AS c FROM pdf_files"
            ).fetchone()["c"]
            autoroutes = self._conn.execute(
                "SELECT COUNT(DISTINCT autoroute) AS c FROM interventions"
                " WHERE autoroute != ''"
            ).fetchone()["c"]
            secteurs = self._conn.execute(
                "SELECT COUNT(DISTINCT secteur) AS c FROM interventions"
                " WHERE secteur != ''"
            ).fetchone()["c"]
            last_update = self._conn.execute(
                "SELECT MAX(updated_at) AS m FROM interventions"
            ).fetchone()["m"]
        return {
            "total": total,
            "terminees": done,
            "a_faire": todo,
            "pdfs": pdfs,
            "autoroutes": autoroutes,
            "secteurs": secteurs,
            "derniere_maj": last_update or "—",
            "db_ok": True,
        }

    def distinct_values(self, column: str) -> list[str]:
        """Retourne les valeurs distinctes non vides d'une colonne autorisée."""
        allowed = {"autoroute", "secteur", "statut", "type_ouvrage"}
        if column not in allowed:
            raise ValueError(f"Colonne non autorisée : {column}")
        with self._lock:
            cur = self._conn.execute(
                f"SELECT DISTINCT {column} AS v FROM interventions"
                f" WHERE {column} != '' ORDER BY {column}"
            )
            rows = cur.fetchall()
        return [r["v"] for r in rows]

    def close(self) -> None:
        """Ferme proprement la connexion SQLite."""
        with self._lock:
            self._conn.commit()
            self._conn.close()
        logger.info("Connexion base fermée.")
