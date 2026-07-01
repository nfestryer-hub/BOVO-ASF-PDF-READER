"""Schemas Pydantic v2 des payloads REST."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import Role


# --------------------------------------------------------------------- #
# Auth
# --------------------------------------------------------------------- #
class LoginRequest(BaseModel):
    """Payload d'appel à ``POST /api/auth/login``."""

    username: str = Field(..., min_length=1, max_length=120)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """Réponse de connexion : tokens + informations utilisateur."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class RefreshRequest(BaseModel):
    """Payload de rafraîchissement du token d'accès."""

    refresh_token: str


class AccessTokenResponse(BaseModel):
    """Réponse contenant uniquement un token d'accès neuf."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


# --------------------------------------------------------------------- #
# Users
# --------------------------------------------------------------------- #
class UserCreate(BaseModel):
    """Payload de création d'utilisateur (Admin uniquement)."""

    username: str = Field(..., min_length=2, max_length=120)
    password: str = Field(..., min_length=4, max_length=200)
    role: Role = Role.CONSULTANT
    full_name: str = ""


class UserOut(BaseModel):
    """Sérialisation publique d'un utilisateur (sans hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: Role
    full_name: str
    is_active: bool
    created_at: datetime
    last_login: datetime | None = None


class UserUpdate(BaseModel):
    """Champs modifiables sur un utilisateur (Admin uniquement)."""

    full_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None


class PasswordChangeRequest(BaseModel):
    """Payload de changement de mot de passe (Admin ou propre compte)."""

    new_password: str = Field(..., min_length=4, max_length=200)


# --------------------------------------------------------------------- #
# Interventions
# --------------------------------------------------------------------- #
class InterventionBase(BaseModel):
    """Champs métier d'une intervention (partagés Read/Create/Update)."""

    ouvrage: str
    objet: str = ""
    autoroute: str = ""
    secteur: str = ""
    pr_debut: str = ""
    pr_fin: str = ""
    sens: str = ""
    longueur: str = ""
    diametre: str = ""
    type_ouvrage: str = ""
    date_debut: str = ""
    date_fin: str = ""
    statut: str = "À planifier"
    pdf_path: str = ""
    commentaire: str = ""


class InterventionCreate(InterventionBase):
    """Payload de création."""


class InterventionUpdate(BaseModel):
    """Payload de mise à jour partielle."""

    objet: str | None = None
    autoroute: str | None = None
    secteur: str | None = None
    pr_debut: str | None = None
    pr_fin: str | None = None
    sens: str | None = None
    longueur: str | None = None
    diametre: str | None = None
    type_ouvrage: str | None = None
    date_debut: str | None = None
    date_fin: str | None = None
    statut: str | None = None
    pdf_path: str | None = None
    commentaire: str | None = None


class InterventionOut(InterventionBase):
    """Sérialisation d'une intervention."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------- #
# Modules dynamiques (inspections/rapports/incidents/matériel)
# --------------------------------------------------------------------- #
class ModuleRowIn(BaseModel):
    """Payload d'écriture d'une ligne de module."""

    data: dict[str, Any] = Field(default_factory=dict)


class ModuleRowOut(BaseModel):
    """Sérialisation d'une ligne de module."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    sheet: str
    data: dict[str, Any]
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------- #
class DocumentOut(BaseModel):
    """Sérialisation d'un document attaché."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    entity: str
    entity_id: str
    filename: str
    mime_type: str
    size_bytes: int
    uploaded_by: str
    uploaded_at: datetime
    notes: str


# --------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------- #
class AuditOut(BaseModel):
    """Sérialisation d'une entrée d'audit."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: str
    action: str
    entity: str
    entity_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    created_at: datetime
