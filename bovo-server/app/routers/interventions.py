"""Router : interventions ASF (planning autoroutier)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app import audit
from app.db import get_db
from app.deps import get_current_user, require_editor
from app.models import Intervention, User
from app.schemas import (
    InterventionCreate, InterventionOut, InterventionUpdate,
)

router = APIRouter(prefix="/api/interventions", tags=["interventions"])


@router.get("", response_model=list[InterventionOut])
def list_interventions(
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    search: Annotated[str, Query(max_length=200)] = "",
    autoroute: Annotated[str, Query(max_length=20)] = "",
    statut: Annotated[str, Query(max_length=40)] = "",
    sort_by: Annotated[str, Query(max_length=20)] = "date",
    sort_dir: Annotated[str, Query(max_length=4)] = "desc",
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InterventionOut]:
    """Retourne les interventions avec filtres, tri et pagination.

    * ``sort_by`` : ``date`` (défaut) ou ``secteur``.
    * ``sort_dir`` : ``asc`` ou ``desc`` (défaut).
    * Pagination : ``limit`` (max 5000) et ``offset``.

    Le tri est toujours déterministe (id DESC en tie-break) pour que la
    pagination soit stable entre appels.
    """
    # Détermine la colonne de tri primaire (fallback = date_debut).
    sort_key = (sort_by or "date").lower()
    if sort_key == "secteur":
        primary = Intervention.secteur
    else:
        primary = Intervention.date_debut
    primary_expr = (
        primary.asc().nullslast() if (sort_dir or "desc").lower() == "asc"
        else primary.desc().nullslast()
    )
    query = select(Intervention).order_by(primary_expr, Intervention.id.desc())
    if search:
        like = f"%{search}%"
        query = query.where(or_(
            Intervention.ouvrage.ilike(like),
            Intervention.objet.ilike(like),
            Intervention.secteur.ilike(like),
        ))
    if autoroute:
        query = query.where(Intervention.autoroute == autoroute)
    if statut:
        query = query.where(Intervention.statut == statut)
    query = query.offset(offset).limit(limit)
    rows = db.scalars(query).all()
    return [InterventionOut.model_validate(r) for r in rows]


@router.post("", response_model=InterventionOut, status_code=status.HTTP_201_CREATED)
def create_intervention(
    payload: InterventionCreate,
    user: Annotated[User, Depends(require_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> InterventionOut:
    """Crée une intervention (Admin ou Planificateur)."""
    existing = db.scalar(
        select(Intervention).where(Intervention.ouvrage == payload.ouvrage)
    )
    if existing is not None:
        # Upsert : on met à jour si l'ouvrage existe déjà.
        for key, value in payload.model_dump(exclude_unset=True).items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        audit.record(
            db, user=user, action="update", entity="intervention",
            entity_id=str(existing.id), after=payload.model_dump(),
        )
        return InterventionOut.model_validate(existing)
    intervention = Intervention(**payload.model_dump())
    db.add(intervention)
    db.commit()
    db.refresh(intervention)
    audit.record(
        db, user=user, action="create", entity="intervention",
        entity_id=str(intervention.id), after=payload.model_dump(),
    )
    return InterventionOut.model_validate(intervention)


@router.get("/{intervention_id}", response_model=InterventionOut)
def get_intervention(
    intervention_id: int,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> InterventionOut:
    intervention = db.get(Intervention, intervention_id)
    if intervention is None:
        raise HTTPException(status_code=404, detail="Intervention introuvable.")
    return InterventionOut.model_validate(intervention)


@router.patch("/{intervention_id}", response_model=InterventionOut)
def update_intervention(
    intervention_id: int, payload: InterventionUpdate,
    user: Annotated[User, Depends(require_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> InterventionOut:
    intervention = db.get(Intervention, intervention_id)
    if intervention is None:
        raise HTTPException(status_code=404, detail="Intervention introuvable.")
    changes = payload.model_dump(exclude_unset=True)
    before = {k: getattr(intervention, k) for k in changes}
    for key, value in changes.items():
        setattr(intervention, key, value)
    db.commit()
    db.refresh(intervention)
    audit.record(
        db, user=user, action="update", entity="intervention",
        entity_id=str(intervention.id), before=before, after=changes,
    )
    return InterventionOut.model_validate(intervention)


@router.delete("/{intervention_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_intervention(
    intervention_id: int,
    user: Annotated[User, Depends(require_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    intervention = db.get(Intervention, intervention_id)
    if intervention is None:
        raise HTTPException(status_code=404, detail="Intervention introuvable.")
    before = {
        "ouvrage": intervention.ouvrage, "objet": intervention.objet,
        "autoroute": intervention.autoroute, "statut": intervention.statut,
    }
    db.delete(intervention)
    db.commit()
    audit.record(
        db, user=user, action="delete", entity="intervention",
        entity_id=str(intervention_id), before=before,
    )
