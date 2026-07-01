"""Utilitaire d'audit trail côté serveur."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.events import publish_sync
from app.models import AuditLog, User


def record(
    db: Session,
    *,
    user: User | None,
    action: str,
    entity: str,
    entity_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    broadcast: bool = True,
) -> None:
    """Enregistre une modification métier dans ``audit_log`` et la diffuse en SSE.

    Args:
        db: Session SQLAlchemy déjà en cours.
        user: Auteur de la modification (peut être ``None`` pour le système).
        action: ``create`` | ``update`` | ``delete`` | ``import``.
        entity: Type d'entité (``intervention``, ``module.inspections``…).
        entity_id: Identifiant de l'entité (chaîne).
        before: État avant modification (sérialisable JSON).
        after: État après modification (sérialisable JSON).
        broadcast: Si ``True``, publie aussi un événement SSE.
    """
    db.add(AuditLog(
        username=user.username if user else "système",
        role=user.role.value if user else "",
        action=action, entity=entity, entity_id=str(entity_id),
        before=before or {}, after=after or {},
    ))
    db.commit()
    if broadcast:
        publish_sync(
            entity=entity, action=action, entity_id=str(entity_id),
            by=user.username if user else "système",
        )
