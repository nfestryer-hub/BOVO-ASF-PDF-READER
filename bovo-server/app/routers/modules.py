"""Router : modules ASF dynamiques (inspections/rapports/incidents/matériel)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import cast, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

from app import audit
from app.db import get_db
from app.deps import get_current_user, require_editor
from app.models import ModuleRow, User
from app.schemas import ModuleRowIn, ModuleRowOut

router = APIRouter(prefix="/api/modules", tags=["modules"])

ALLOWED_SHEETS: set[str] = {"inspections", "rapports", "incidents", "materiel"}


def _validate_sheet(sheet: str) -> None:
    if sheet not in ALLOWED_SHEETS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Module inconnu. Attendu : {sorted(ALLOWED_SHEETS)}",
        )


@router.get("/{sheet}", response_model=list[ModuleRowOut])
def list_rows(
    sheet: str,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    search: Annotated[str, Query(max_length=200)] = "",
) -> list[ModuleRowOut]:
    """Liste toutes les lignes d'un module (ordre décroissant par id)."""
    _validate_sheet(sheet)
    query = select(ModuleRow).where(ModuleRow.sheet == sheet).order_by(ModuleRow.id.desc())
    if search:
        # Recherche sur toutes les valeurs texte du JSONB.
        like = f"%{search.lower()}%"
        query = query.where(cast(ModuleRow.data, JSONB).cast(str).ilike(like))
    rows = db.scalars(query).all()
    return [ModuleRowOut.model_validate(r) for r in rows]


@router.post("/{sheet}", response_model=ModuleRowOut, status_code=status.HTTP_201_CREATED)
def create_row(
    sheet: str, payload: ModuleRowIn,
    user: Annotated[User, Depends(require_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> ModuleRowOut:
    """Crée une ligne dans le module ciblé (Admin ou Planificateur)."""
    _validate_sheet(sheet)
    row = ModuleRow(sheet=sheet, data=payload.data)
    db.add(row)
    db.commit()
    db.refresh(row)
    audit.record(
        db, user=user, action="create", entity=f"module.{sheet}",
        entity_id=str(row.id), after=payload.data,
    )
    return ModuleRowOut.model_validate(row)


@router.patch("/{sheet}/{row_id}", response_model=ModuleRowOut)
def update_row(
    sheet: str, row_id: int, payload: ModuleRowIn,
    user: Annotated[User, Depends(require_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> ModuleRowOut:
    """Met à jour intégralement une ligne (Admin ou Planificateur)."""
    _validate_sheet(sheet)
    row = db.get(ModuleRow, row_id)
    if row is None or row.sheet != sheet:
        raise HTTPException(status_code=404, detail="Ligne introuvable.")
    before = dict(row.data)
    row.data = payload.data
    db.commit()
    db.refresh(row)
    audit.record(
        db, user=user, action="update", entity=f"module.{sheet}",
        entity_id=str(row.id), before=before, after=payload.data,
    )
    return ModuleRowOut.model_validate(row)


@router.delete("/{sheet}/{row_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_row(
    sheet: str, row_id: int,
    user: Annotated[User, Depends(require_editor)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Supprime une ligne (Admin ou Planificateur)."""
    _validate_sheet(sheet)
    row = db.get(ModuleRow, row_id)
    if row is None or row.sheet != sheet:
        raise HTTPException(status_code=404, detail="Ligne introuvable.")
    before = dict(row.data)
    db.delete(row)
    db.commit()
    audit.record(
        db, user=user, action="delete", entity=f"module.{sheet}",
        entity_id=str(row_id), before=before,
    )
