"""Authentification locale de Bovo ASF Manager.

Auth mono-poste (SQLite locale) — trois rôles :

* :class:`Role.ADMIN` — accès total + gestion des utilisateurs.
* :class:`Role.PLANIFICATEUR` — accès total sauf gestion des utilisateurs.
* :class:`Role.CONSULTANT` — lecture seule + pas d'accès au planning
  (Calendrier / Interventions).

Pas de JWT ni de cookies (contexte desktop). La session est simplement
mémorisée dans l'objet :class:`AuthService`. Les mots de passe sont hachés
via **bcrypt** (coût 12).

Le seed initial est idempotent :

* si un utilisateur n'existe pas → il est créé ;
* s'il existe mais que le hash ne correspond plus au mot de passe voulu,
  le hash est mis à jour (ex. rotation du mot de passe par défaut).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import bcrypt

from app.database import Database
from app.logger import LogAction, LogLevel, get_logger, log_action

logger = get_logger("auth")

_BCRYPT_COST = 12


class Role(str, Enum):
    """Rôles de sécurité du logiciel.

    ============================  ======================================
    Rôle                          Droits
    ============================  ======================================
    ADMIN                         Accès total, y compris utilisateurs
                                  et historique.
    INSPECTEUR_ITV                Comme Admin, MAIS pas de journal /
                                  historique / gestion des utilisateurs.
    PLANIFICATEUR                 Accueil + Import PDF + Calendrier +
                                  Interventions (tous droits).
                                  Inspections ASF en LECTURE SEULE.
                                  Pas de journal / historique / users.
    CONSULTANT                    Lecture seule + pas d'accès au
                                  planning (Calendrier + Interventions).
    ============================  ======================================
    """

    ADMIN = "Admin"
    INSPECTEUR_ITV = "Inspecteur ITV"
    PLANIFICATEUR = "Planificateur"
    CONSULTANT = "Consultant"

    @classmethod
    def from_value(cls, value: str) -> Role:
        """Retourne le rôle correspondant, ou :attr:`CONSULTANT` par défaut."""
        for role in cls:
            if role.value == value:
                return role
        return cls.CONSULTANT


@dataclass(slots=True)
class User:
    """Utilisateur authentifié."""

    id: int | None
    username: str
    role: Role
    full_name: str = ""
    created_at: str = ""
    last_login: str = ""

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> User:
        """Construit un ``User`` depuis une ligne SQLite (sans le hash)."""
        return cls(
            id=row.get("id"),
            username=row["username"],
            role=Role.from_value(row.get("role", Role.CONSULTANT.value)),
            full_name=row.get("full_name", ""),
            created_at=row.get("created_at", ""),
            last_login=row.get("last_login", ""),
        )


#: Utilisateurs seedés au premier lancement (idempotent).
DEFAULT_USERS: tuple[dict[str, str], ...] = (
    {
        "username": "Bovo", "password": "ibak23",
        "role": Role.ADMIN.value, "full_name": "Administrateur BOVO",
    },
    {
        "username": "Dylan HENRI", "password": "0811048re55Ol5!",
        "role": Role.PLANIFICATEUR.value, "full_name": "Dylan HENRI",
    },
    {
        "username": "ASF", "password": "asfmontauban!",
        "role": Role.CONSULTANT.value, "full_name": "Consultant ASF",
    },
)


def hash_password(plain: str) -> str:
    """Hache un mot de passe en clair (bcrypt, coût 12)."""
    return bcrypt.hashpw(
        plain.encode("utf-8"), bcrypt.gensalt(rounds=_BCRYPT_COST)
    ).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Vérifie un mot de passe en clair contre un hash bcrypt."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


@dataclass(slots=True)
class Session:
    """Session courante (en mémoire uniquement)."""

    user: User | None = field(default=None)

    @property
    def is_authenticated(self) -> bool:
        """``True`` si un utilisateur est authentifié."""
        return self.user is not None

    @property
    def role(self) -> Role | None:
        """Rôle courant, ``None`` si non connecté."""
        return self.user.role if self.user else None

    def can_edit(self) -> bool:
        """Vrai pour Admin, Inspecteur ITV et Planificateur (édition interventions / calendrier)."""
        return self.role in (
            Role.ADMIN, Role.INSPECTEUR_ITV, Role.PLANIFICATEUR,
        )

    def can_edit_inspections(self) -> bool:
        """Édition des Inspections ASF (modules éditables).

        Le Planificateur a un accès en LECTURE SEULE ici — il peut
        consulter mais pas modifier ni supprimer les rapports, incidents,
        matériel. Admin et Inspecteur ITV ont tous les droits.
        """
        return self.role in (Role.ADMIN, Role.INSPECTEUR_ITV)

    def can_view_planning(self) -> bool:
        """Le Consultant n'a pas accès au planning (Calendrier + Interventions)."""
        return self.role in (
            Role.ADMIN, Role.INSPECTEUR_ITV, Role.PLANIFICATEUR,
        )

    def can_import_pdf(self) -> bool:
        """Import PDF : Admin, Inspecteur ITV et Planificateur uniquement."""
        return self.role in (
            Role.ADMIN, Role.INSPECTEUR_ITV, Role.PLANIFICATEUR,
        )

    def can_manage_users(self) -> bool:
        """Seul l'Admin peut gérer les utilisateurs."""
        return self.role is Role.ADMIN

    def can_view_audit(self) -> bool:
        """Seul l'Admin peut consulter l'historique / le journal.

        Inspecteur ITV et Planificateur n'y ont plus accès (rétention V1.2).
        """
        return self.role is Role.ADMIN


class AuthService:
    """Service d'authentification et de gestion des utilisateurs."""

    def __init__(self, database: Database) -> None:
        """Initialise le service et seed les utilisateurs par défaut."""
        self._db = database
        self._db.ensure_users_table()
        self._session = Session()
        self.seed_default_users()

    # ------------------------------------------------------------------ #
    # Seed idempotent
    # ------------------------------------------------------------------ #
    def seed_default_users(self) -> int:
        """Crée les utilisateurs par défaut ou met à jour le hash si obsolète.

        Returns:
            Le nombre d'utilisateurs créés ou mis à jour.
        """
        changed = 0
        for spec in DEFAULT_USERS:
            existing = self._db.get_user_by_username(spec["username"])
            if existing is None:
                self._db.insert_user(
                    username=spec["username"],
                    password_hash=hash_password(spec["password"]),
                    role=spec["role"],
                    full_name=spec["full_name"],
                )
                changed += 1
                continue
            if not verify_password(spec["password"], existing["password_hash"]):
                self._db.update_user_password(
                    int(existing["id"]), hash_password(spec["password"])
                )
                changed += 1
        if changed:
            logger.info("Seed utilisateurs : %d utilisateur(s) créés/actualisés.", changed)
        return changed

    # ------------------------------------------------------------------ #
    # Login / Logout
    # ------------------------------------------------------------------ #
    def login(self, username: str, password: str) -> User | None:
        """Tente de connecter un utilisateur. Retourne l'objet User ou ``None``."""
        username = (username or "").strip()
        row = self._db.get_user_by_username(username)
        if row is None or not verify_password(password, row["password_hash"]):
            log_action(
                self._db, LogAction.OPEN,
                f"Échec de connexion pour « {username} ».",
                level=LogLevel.WARNING,
            )
            return None
        now = datetime.now(UTC).isoformat()
        self._db.touch_user_login(int(row["id"]), now)
        user = User.from_row({**row, "last_login": now})
        self._session.user = user
        log_action(
            self._db, LogAction.OPEN,
            f"Connexion réussie : {user.username} ({user.role.value}).",
            level=LogLevel.SUCCESS,
        )
        return user

    def logout(self) -> None:
        """Termine la session courante."""
        if self._session.user is not None:
            log_action(
                self._db, LogAction.CLOSE,
                f"Déconnexion : {self._session.user.username}.",
            )
        self._session.user = None

    def try_auto_login(self, username: str, stored_hash: str) -> User | None:
        """Tente une reconnexion silencieuse avec un hash déjà validé.

        Utilisé par la case « Se souvenir de moi » : au lancement suivant,
        on relit le username + le hash stocké localement (dans les settings)
        et on vérifie qu'il correspond bien au hash actuel en base. Si oui,
        l'utilisateur est reconnecté sans saisie.

        Args:
            username: Nom d'utilisateur mémorisé.
            stored_hash: Hash bcrypt persisté côté client.

        Returns:
            L'utilisateur reconnecté, ou ``None`` si le hash ne correspond
            plus (mot de passe changé côté serveur) ou si l'utilisateur
            n'existe plus.
        """
        username = (username or "").strip()
        if not username or not stored_hash:
            return None
        row = self._db.get_user_by_username(username)
        if row is None or row["password_hash"] != stored_hash:
            return None
        now = datetime.now(UTC).isoformat()
        self._db.touch_user_login(int(row["id"]), now)
        user = User.from_row({**row, "last_login": now})
        self._session.user = user
        log_action(
            self._db, LogAction.OPEN,
            f"Reconnexion automatique : {user.username}.",
            level=LogLevel.SUCCESS,
        )
        return user

    # ------------------------------------------------------------------ #
    # Session
    # ------------------------------------------------------------------ #
    @property
    def session(self) -> Session:
        """Retourne la session courante."""
        return self._session

    @property
    def current_user(self) -> User | None:
        """Utilisateur courant, ou ``None`` si non connecté."""
        return self._session.user

    # ------------------------------------------------------------------ #
    # Administration des utilisateurs
    # ------------------------------------------------------------------ #
    def list_users(self) -> list[User]:
        """Liste tous les utilisateurs (sans exposer les hashs)."""
        return [User.from_row(row) for row in self._db.list_users()]

    def create_user(
        self, username: str, password: str, role: Role, full_name: str = ""
    ) -> User:
        """Crée un nouvel utilisateur (Admin uniquement — vérifier au niveau GUI).

        Raises:
            ValueError: Si le nom d'utilisateur est vide ou déjà pris.
        """
        username = username.strip()
        if not username:
            raise ValueError("Nom d'utilisateur requis.")
        if not password:
            raise ValueError("Mot de passe requis.")
        if self._db.get_user_by_username(username) is not None:
            raise ValueError("Nom d'utilisateur déjà utilisé.")
        new_id = self._db.insert_user(
            username=username,
            password_hash=hash_password(password),
            role=role.value,
            full_name=full_name,
        )
        log_action(
            self._db, LogAction.CREATE,
            f"Utilisateur créé : {username} ({role.value}).",
            level=LogLevel.SUCCESS,
        )
        return User(
            id=new_id, username=username, role=role, full_name=full_name,
            created_at=datetime.now(UTC).isoformat(),
        )

    def change_password(self, user_id: int, new_password: str) -> None:
        """Modifie le mot de passe d'un utilisateur."""
        if not new_password:
            raise ValueError("Mot de passe requis.")
        self._db.update_user_password(user_id, hash_password(new_password))
        log_action(
            self._db, LogAction.UPDATE,
            f"Mot de passe modifié (utilisateur #{user_id}).",
            level=LogLevel.SUCCESS,
        )

    def delete_user(self, user_id: int) -> None:
        """Supprime un utilisateur. Refuse la suppression de soi-même."""
        if self._session.user and self._session.user.id == user_id:
            raise ValueError("Vous ne pouvez pas supprimer votre propre compte.")
        self._db.delete_user(user_id)
        log_action(
            self._db, LogAction.DELETE,
            f"Utilisateur supprimé (id={user_id}).",
            level=LogLevel.WARNING,
        )


__all__ = [
    "DEFAULT_USERS", "AuthService", "Role", "Session", "User",
    "hash_password", "verify_password",
]
