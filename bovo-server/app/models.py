"""Modèles SQLAlchemy 2.0 de Bovo ASF Manager Server.

Chaque table métier suit une convention commune : ``id`` auto-incrémenté,
``created_at`` et ``updated_at`` horodatés en UTC. Les modules ASF
(inspections / rapports / incidents / matériel) sont stockés dans des tables
distinctes mais partagent la même forme dynamique.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON, BigInteger, Boolean, DateTime, Enum, ForeignKey, Index, Integer,
    String, Text, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Role(str, PyEnum):
    """Rôles applicatifs de Bovo ASF Manager."""

    ADMIN = "Admin"
    PLANIFICATEUR = "Planificateur"
    CONSULTANT = "Consultant"


class User(Base):
    """Utilisateur du logiciel avec authentification bcrypt + JWT."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(Enum(Role), nullable=False, default=Role.CONSULTANT)
    full_name: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )


class LoginAttempt(Base):
    """Traçage des tentatives de connexion pour la protection anti-brute force."""

    __tablename__ = "login_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    identifier: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    successful: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True,
    )


class Intervention(Base):
    """Intervention ASF (planning autoroutier) issue du parseur PDF."""

    __tablename__ = "interventions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ouvrage: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    objet: Mapped[str] = mapped_column(String(255), default="")
    autoroute: Mapped[str] = mapped_column(String(20), default="", index=True)
    secteur: Mapped[str] = mapped_column(String(120), default="")
    pr_debut: Mapped[str] = mapped_column(String(20), default="")
    pr_fin: Mapped[str] = mapped_column(String(20), default="")
    sens: Mapped[str] = mapped_column(String(30), default="")
    type_ouvrage: Mapped[str] = mapped_column(String(60), default="")
    date_debut: Mapped[str] = mapped_column(String(20), default="")
    date_fin: Mapped[str] = mapped_column(String(20), default="")
    statut: Mapped[str] = mapped_column(String(40), default="À planifier", nullable=False)
    pdf_path: Mapped[str] = mapped_column(String(400), default="")
    observations: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=lambda: datetime.now(UTC), nullable=False,
    )


class ModuleRow(Base):
    """Ligne d'un module ASF (inspections/rapports/incidents/matériel).

    Utilise une colonne JSONB pour supporter les champs dynamiques sans
    migrations à chaque nouveau champ. La colonne ``sheet`` identifie le
    module. Un index composite ``(sheet, id)`` accélère les listings par
    module.
    """

    __tablename__ = "module_rows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sheet: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=lambda: datetime.now(UTC), nullable=False,
    )


Index("idx_module_rows_sheet", ModuleRow.sheet)


class Document(Base):
    """Document attaché à une entité (métadonnées ; fichier hors DB)."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), default="")
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    uploaded_by: Mapped[str] = mapped_column(String(120), default="")
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    notes: Mapped[str] = mapped_column(Text, default="")


class AuditLog(Base):
    """Journal des modifications (qui a fait quoi et quand)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(120), default="système", index=True)
    role: Mapped[str] = mapped_column(String(40), default="")
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    entity: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True,
    )


class Setting(Base):
    """Paramètres globaux du serveur (référentiels, options)."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
    )
