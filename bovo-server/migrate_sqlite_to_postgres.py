"""Script one-shot : migration de la base SQLite locale vers PostgreSQL.

Usage
-----

Sur le VPS (après avoir démarré la pile ``docker compose up -d``) :

1. Copiez le fichier ``bovo.db`` du client vers ``/opt/bovo/bovo.db``.
2. Assurez-vous que ``POSTGRES_DSN`` pointe sur la base cible.
3. Lancez :

.. code-block:: bash

    python migrate_sqlite_to_postgres.py --sqlite /opt/bovo/bovo.db

Le script est **idempotent** : il ne double pas les lignes déjà présentes
(recherche par ``ouvrage`` pour les interventions et par colonne ``id``
pour les autres tables). Les utilisateurs déjà seedés ne sont pas
remplacés.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine
from app.models import (
    AuditLog, Document, Intervention, ModuleRow, Role, Setting, User,
)


def _iso(value: str) -> datetime | None:
    """Convertit une chaîne ISO en datetime (UTC) sans planter."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _migrate_users(sqlite_db: sqlite3.Connection, db: Session) -> int:
    """Migre la table ``users``. Idempotent par ``username``."""
    rows = sqlite_db.execute("SELECT * FROM users").fetchall()
    added = 0
    for row in rows:
        existing = db.query(User).filter(User.username == row["username"]).first()
        if existing is not None:
            continue
        db.add(User(
            username=row["username"], password_hash=row["password_hash"],
            role=Role(row["role"]), full_name=row.get("full_name") or "",
            created_at=_iso(row.get("created_at")) or datetime.now(UTC),
            last_login=_iso(row.get("last_login")),
        ))
        added += 1
    db.commit()
    return added


def _migrate_interventions(sqlite_db: sqlite3.Connection, db: Session) -> int:
    """Migre les interventions ASF. Idempotent par ``ouvrage``."""
    rows = sqlite_db.execute("SELECT * FROM interventions").fetchall()
    added = 0
    for row in rows:
        existing = db.query(Intervention).filter(
            Intervention.ouvrage == row["ouvrage"]
        ).first()
        if existing is not None:
            continue
        db.add(Intervention(
            ouvrage=row["ouvrage"], objet=row.get("objet") or "",
            autoroute=row.get("autoroute") or "", secteur=row.get("secteur") or "",
            pr_debut=row.get("pr_debut") or "", pr_fin=row.get("pr_fin") or "",
            sens=row.get("sens") or "", type_ouvrage=row.get("type_ouvrage") or "",
            date_debut=row.get("date_debut") or "", date_fin=row.get("date_fin") or "",
            statut=row.get("statut") or "À planifier",
            pdf_path=row.get("pdf_path") or "",
            observations=row.get("observations") or "",
        ))
        added += 1
    db.commit()
    return added


def _migrate_module(
    sqlite_db: sqlite3.Connection, db: Session, sheet: str,
) -> int:
    """Migre un module ASF vers ``module_rows`` (JSONB)."""
    try:
        rows = sqlite_db.execute(f'SELECT * FROM "{sheet}"').fetchall()
    except sqlite3.OperationalError:
        return 0
    added = 0
    for row in rows:
        data = {k: row[k] for k in row.keys() if k not in ("id", "created_at", "updated_at")}
        # Reprend l'``id`` d'origine pour préserver les références.
        existing = db.query(ModuleRow).filter(
            ModuleRow.sheet == sheet, ModuleRow.id == row["id"]
        ).first()
        if existing is not None:
            continue
        db.add(ModuleRow(id=row["id"], sheet=sheet, data=data))
        added += 1
    db.commit()
    return added


def _migrate_documents(sqlite_db: sqlite3.Connection, db: Session) -> int:
    """Migre les métadonnées de documents. Copie physique à faire manuellement."""
    try:
        rows = sqlite_db.execute("SELECT * FROM documents").fetchall()
    except sqlite3.OperationalError:
        return 0
    added = 0
    for row in rows:
        existing = db.query(Document).filter(Document.id == row["id"]).first()
        if existing is not None:
            continue
        db.add(Document(
            id=row["id"], entity=row["entity"], entity_id=row["entity_id"],
            filename=row["filename"], storage_path=row["storage_path"],
            mime_type=row.get("mime_type") or "",
            size_bytes=int(row.get("size_bytes") or 0),
            uploaded_by=row.get("uploaded_by") or "",
            uploaded_at=_iso(row.get("uploaded_at")) or datetime.now(UTC),
            notes=row.get("notes") or "",
        ))
        added += 1
    db.commit()
    return added


def _migrate_settings(sqlite_db: sqlite3.Connection, db: Session) -> int:
    """Migre la table ``settings`` (paramètres et référentiels)."""
    try:
        rows = sqlite_db.execute("SELECT * FROM settings").fetchall()
    except sqlite3.OperationalError:
        return 0
    added = 0
    for row in rows:
        key = row["key"]
        if db.get(Setting, key) is not None:
            continue
        try:
            value = json.loads(row["value"]) if row.get("value") else {}
        except (TypeError, json.JSONDecodeError):
            value = {"raw": row.get("value") or ""}
        if not isinstance(value, dict):
            value = {"value": value}
        db.add(Setting(key=key, value=value))
        added += 1
    db.commit()
    return added


def _migrate_audit(sqlite_db: sqlite3.Connection, db: Session) -> int:
    """Migre l'audit trail existant."""
    try:
        rows = sqlite_db.execute("SELECT * FROM audit_log").fetchall()
    except sqlite3.OperationalError:
        return 0
    added = 0
    for row in rows:
        try:
            before = json.loads(row.get("before_json") or "{}")
        except json.JSONDecodeError:
            before = {}
        try:
            after = json.loads(row.get("after_json") or "{}")
        except json.JSONDecodeError:
            after = {}
        db.add(AuditLog(
            username=row.get("username") or "système",
            role=row.get("role") or "",
            action=row["action"], entity=row["entity"],
            entity_id=row["entity_id"], before=before, after=after,
            created_at=_iso(row.get("created_at")) or datetime.now(UTC),
        ))
        added += 1
    db.commit()
    return added


def main() -> int:
    """CLI d'entrée."""
    parser = argparse.ArgumentParser(description="Migration SQLite → PostgreSQL.")
    parser.add_argument("--sqlite", required=True, type=Path, help="Chemin bovo.db")
    args = parser.parse_args()

    if not args.sqlite.exists():
        print(f"❌ SQLite introuvable : {args.sqlite}", file=sys.stderr)
        return 1

    Base.metadata.create_all(bind=engine)
    sqlite_db = sqlite3.connect(str(args.sqlite))
    sqlite_db.row_factory = sqlite3.Row

    with SessionLocal() as db:
        users = _migrate_users(sqlite_db, db)
        interventions = _migrate_interventions(sqlite_db, db)
        modules = {
            s: _migrate_module(sqlite_db, db, s)
            for s in ("inspections", "rapports", "incidents", "materiel")
        }
        docs = _migrate_documents(sqlite_db, db)
        settings = _migrate_settings(sqlite_db, db)
        audits = _migrate_audit(sqlite_db, db)

    sqlite_db.close()
    print("✅ Migration terminée")
    print(f"   Utilisateurs      : {users}")
    print(f"   Interventions     : {interventions}")
    for sheet, count in modules.items():
        print(f"   Module {sheet:12s}: {count}")
    print(f"   Documents (méta)  : {docs}")
    print(f"   Paramètres        : {settings}")
    print(f"   Audit log         : {audits}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
