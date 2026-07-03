"""Historique des modifications (audit trail) de Bovo ASF Manager.

Enregistre pour chaque écriture métier :

* l'auteur (username / rôle) ;
* l'action (``create`` / ``update`` / ``delete``) ;
* l'entité concernée (``intervention``, ``rapport``, ``inspection`` …) ;
* le ``before`` et ``after`` sérialisés en JSON pour un diff éclairé.

Le module reste indépendant du GUI : les services métier appellent
:class:`AuditService` avant/après chaque modification.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.database import Database
from app.logger import get_logger

logger = get_logger("audit")


@dataclass(slots=True)
class AuditEntry:
    """Ligne de l'audit trail."""

    id: int
    username: str
    role: str
    action: str
    entity: str
    entity_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    created_at: str

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> AuditEntry:
        """Construit une entrée d'audit depuis une ligne SQLite."""
        return cls(
            id=int(row["id"]),
            username=row.get("username", "") or "",
            role=row.get("role", "") or "",
            action=row.get("action", "") or "",
            entity=row.get("entity", "") or "",
            entity_id=row.get("entity_id", "") or "",
            before=_safe_json_loads(row.get("before_json")),
            after=_safe_json_loads(row.get("after_json")),
            created_at=row.get("created_at", "") or "",
        )

    def diff(self) -> list[tuple[str, Any, Any]]:
        """Retourne la liste des différences ``(champ, avant, après)``.

        Les champs internes techniques (``id``, ``created_at``, ``updated_at``)
        sont volontairement filtrés pour ne présenter que le diff métier.
        """
        ignore = {"id", "created_at", "updated_at"}
        keys = sorted((set(self.before) | set(self.after)) - ignore)
        result: list[tuple[str, Any, Any]] = []
        for key in keys:
            before = self.before.get(key, "")
            after = self.after.get(key, "")
            if before != after:
                result.append((key, before, after))
        return result


def _safe_json_loads(value: Any) -> dict[str, Any]:
    """Convertit une chaîne JSON en dict, ou dict vide en cas d'erreur."""
    if not value:
        return {}
    try:
        data = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


class AuditService:
    """Service d'enregistrement et de consultation de l'audit trail."""

    def __init__(self, database: Database) -> None:
        """Initialise le service et garantit la table ``audit_log``."""
        self._db = database
        self._db.ensure_audit_table()
        self._username: str = "système"
        self._role: str = ""

    def bind_session(self, username: str, role: str) -> None:
        """Attache la session courante (appelé après login)."""
        self._username = username or "système"
        self._role = role or ""

    # ------------------------------------------------------------------ #
    # Écriture
    # ------------------------------------------------------------------ #
    def record(
        self,
        *,
        action: str,
        entity: str,
        entity_id: str,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        """Enregistre une modification dans l'audit trail."""
        self._db.insert_audit(
            username=self._username, role=self._role,
            action=action, entity=entity, entity_id=str(entity_id),
            before_json=json.dumps(before or {}, ensure_ascii=False, default=str),
            after_json=json.dumps(after or {}, ensure_ascii=False, default=str),
            created_at=datetime.now(UTC).isoformat(),
        )

    # ------------------------------------------------------------------ #
    # Lecture
    # ------------------------------------------------------------------ #
    def list_entries(
        self, limit: int = 500, entity: str = "", search: str = ""
    ) -> list[AuditEntry]:
        """Retourne les entrées de l'audit trail (filtres optionnels)."""
        rows = self._db.list_audit(limit=limit, entity=entity, search=search)
        return [AuditEntry.from_row(r) for r in rows]


__all__ = ["AuditEntry", "AuditService"]
