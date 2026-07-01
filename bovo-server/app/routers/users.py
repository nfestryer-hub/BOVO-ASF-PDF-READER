"""Router : gestion des utilisateurs (Admin uniquement)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import audit
from app.db import get_db
from app.deps import get_current_user, require_admin
from app.models import Role, User
from app.schemas import (
    PasswordChangeRequest, UserCreate, UserOut, UserUpdate,
)
from app.security import hash_password

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    _admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> list[UserOut]:
    """Liste tous les utilisateurs (Admin uniquement)."""
    users = db.scalars(select(User).order_by(User.username)).all()
    return [UserOut.model_validate(u) for u in users]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> UserOut:
    """Crée un utilisateur (Admin uniquement)."""
    existing = db.scalar(select(User).where(User.username == payload.username))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Nom d'utilisateur déjà utilisé.",
        )
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=payload.role, full_name=payload.full_name,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.record(
        db, user=admin, action="create", entity="user",
        entity_id=str(user.id),
        after={"username": user.username, "role": user.role.value,
               "full_name": user.full_name},
    )
    return UserOut.model_validate(user)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, payload: UserUpdate,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> UserOut:
    """Met à jour un utilisateur (Admin uniquement)."""
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    before = {"full_name": user.full_name, "role": user.role.value,
              "is_active": user.is_active}
    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    audit.record(
        db, user=admin, action="update", entity="user",
        entity_id=str(user.id),
        before=before,
        after={"full_name": user.full_name, "role": user.role.value,
               "is_active": user.is_active},
    )
    return UserOut.model_validate(user)


@router.post("/{user_id}/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    user_id: int, payload: PasswordChangeRequest,
    current: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Change le mot de passe d'un utilisateur.

    * Un utilisateur peut changer son propre mot de passe.
    * L'Admin peut changer celui d'un autre utilisateur.
    """
    if current.role != Role.ADMIN and current.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Vous ne pouvez modifier que votre propre mot de passe.",
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    audit.record(
        db, user=current, action="update", entity="user.password",
        entity_id=str(user.id),
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: int,
    admin: Annotated[User, Depends(require_admin)],
    db: Annotated[Session, Depends(get_db)],
) -> None:
    """Supprime un utilisateur (Admin uniquement, sauf soi-même)."""
    if admin.id == user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vous ne pouvez pas supprimer votre propre compte.",
        )
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable.")
    before = {"username": user.username, "role": user.role.value}
    db.delete(user)
    db.commit()
    audit.record(
        db, user=admin, action="delete", entity="user",
        entity_id=str(user_id), before=before,
    )
