"""Session utilisateur côté client (mode serveur REST).

Encapsule l'état de connexion (utilisateur courant, rôle, tokens JWT) et
expose les mêmes helpers de permissions que l'ancienne classe locale
:class:`app.auth.Session`. La vérité vient désormais du serveur — le rôle
est celui retourné par ``/api/auth/me`` (ou lu dans la réponse de
``/api/auth/login``). Aucun accès à SQLite ici.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.api_client import ApiClient

_EDIT_ROLES = {"Admin", "Planificateur"}
_ADMIN_ROLES = {"Admin"}
_PLANNING_ROLES = {"Admin", "Planificateur"}
_AUDIT_ROLES = {"Admin", "Planificateur"}


@dataclass(slots=True)
class RemoteUser:
    """Utilisateur retourné par l'API. Sert d'objet compatible avec l'UI."""

    id: int | None
    username: str
    role: str
    full_name: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RemoteUser:
        """Construit un utilisateur à partir du JSON renvoyé par l'API."""
        return cls(
            id=data.get("id"),
            username=data.get("username", ""),
            role=data.get("role", "Consultant"),
            full_name=data.get("full_name", ""),
        )


@dataclass
class Session:
    """Session courante du client Bovo ASF Manager.

    Contient l'instance unique de :class:`ApiClient` et l'utilisateur
    connecté. Les vues GUI accèdent aux permissions via ``can_*``.
    """

    client: ApiClient
    user: RemoteUser | None = field(default=None)

    # ------------------------------------------------------------------ #
    # État
    # ------------------------------------------------------------------ #
    @property
    def is_authenticated(self) -> bool:
        """Vrai si un utilisateur est connecté."""
        return self.user is not None

    @property
    def username(self) -> str:
        """Nom de l'utilisateur courant (chaîne vide si non connecté)."""
        return self.user.username if self.user else ""

    @property
    def role(self) -> str:
        """Rôle courant (``"Consultant"`` par défaut si non connecté)."""
        return self.user.role if self.user else "Consultant"

    # ------------------------------------------------------------------ #
    # Cycle de vie
    # ------------------------------------------------------------------ #
    def bind(self, user_data: dict[str, Any]) -> RemoteUser:
        """Enregistre l'utilisateur connecté à partir du payload API."""
        self.user = RemoteUser.from_dict(user_data)
        return self.user

    def clear(self) -> None:
        """Efface la session courante (logout local)."""
        self.user = None
        self.client.logout()

    # ------------------------------------------------------------------ #
    # Permissions (miroir de l'ancien AuthService.Session)
    # ------------------------------------------------------------------ #
    def can_edit(self) -> bool:
        """Vrai pour Admin et Planificateur."""
        return self.role in _EDIT_ROLES

    def can_view_planning(self) -> bool:
        """Le Consultant n'a pas accès au planning."""
        return self.role in _PLANNING_ROLES

    def can_manage_users(self) -> bool:
        """Seul l'Admin peut gérer les utilisateurs."""
        return self.role in _ADMIN_ROLES

    def can_view_audit(self) -> bool:
        """Admin et Planificateur peuvent consulter l'historique."""
        return self.role in _AUDIT_ROLES
