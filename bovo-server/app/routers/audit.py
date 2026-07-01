"""Router : consultation du journal d'audit (Admin + Planificateur)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import require_editor
from app.models import AuditLog, User
from app.schemas import AuditOut

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditOut])
def list_audit(
    _user: Annotated[User, Depends(require_editor)],
    db: Annotated[Session, Depends(get_db)],
    entity: Annotated[str, Query(max_length=40)] = "",
    search: Annotated[str, Query(max_length=200)] = "",
    limit: Annotated[int, Query(ge=1, le=1000)] = 300,
) -> list[AuditOut]:
    """Retourne les dernières entrées d'audit selon les filtres."""
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if entity:
        query = query.where(AuditLog.entity == entity)
    if search:
        like = f"%{search}%"
        query = query.where(or_(
            AuditLog.username.ilike(like),
            AuditLog.entity.ilike(like),
            AuditLog.entity_id.ilike(like),
        ))
    rows = db.scalars(query).all()
    return [AuditOut.model_validate(r) for r in rows]
