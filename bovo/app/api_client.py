"""Client REST du serveur Bovo ASF Manager.

Ce module encapsule toutes les interactions avec l'API centralisée. Il gère :

* le stockage local sécurisé des tokens (access + refresh) dans les settings ;
* le rafraîchissement automatique du token à l'expiration (401) ;
* les timeouts et la conversion des erreurs HTTP en exceptions Python typées.

Utilisation minimale::

    client = ApiClient(base_url="https://bovo.exemple.fr")
    user = client.login("Bovo", "ibak23")           # -> dict user info
    interventions = client.list_interventions()      # -> list[dict]
    intervention = client.create_intervention({
        "ouvrage": "12345", "objet": "Curage", ...
    })
    client.close()

Toutes les méthodes lèvent :class:`ApiError` en cas de non-2xx (avec le code
HTTP et le message ``detail`` renvoyé par le backend).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from requests import Response

logger = logging.getLogger("bovo.api")

_DEFAULT_TIMEOUT = 15.0
_UPLOAD_TIMEOUT = 120.0


class ApiError(RuntimeError):
    """Erreur remontée par le serveur (code HTTP + détail)."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"[{status_code}] {detail}")
        self.status_code = status_code
        self.detail = detail


@dataclass(slots=True)
class Tokens:
    """Couple de tokens JWT retournés par ``/api/auth/login``."""

    access_token: str = ""
    refresh_token: str = ""
    expires_in: int = 0
    user: dict[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Vrai si un token d'accès est présent."""
        return bool(self.access_token)


class ApiClient:
    """Client HTTP autour de l'API Bovo ASF Manager Server.

    Args:
        base_url: URL racine du backend (ex. ``https://bovo.exemple.fr``).
            Le suffixe ``/api`` est ajouté automatiquement à chaque appel.
        timeout: Timeout en secondes appliqué à chaque requête.

    Le client est **thread-safe pour les requêtes** grâce à ``requests.Session``.
    Le rafraîchissement de token est protégé par un lock explicite.
    """

    def __init__(self, base_url: str, timeout: float = _DEFAULT_TIMEOUT) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()
        self._tokens = Tokens()

    # ------------------------------------------------------------------ #
    # Session lifecycle
    # ------------------------------------------------------------------ #
    def set_tokens(self, access_token: str, refresh_token: str = "") -> None:
        """Restaure une session existante (auto-login au lancement)."""
        self._tokens = Tokens(access_token=access_token, refresh_token=refresh_token)

    @property
    def tokens(self) -> Tokens:
        """Retourne la session courante (tokens + info user)."""
        return self._tokens

    @property
    def base_url(self) -> str:
        """URL racine du backend."""
        return self._base_url

    def close(self) -> None:
        """Ferme la session HTTP."""
        self._session.close()

    # ------------------------------------------------------------------ #
    # Low-level HTTP
    # ------------------------------------------------------------------ #
    def _url(self, path: str) -> str:
        """Construit l'URL absolue d'un endpoint (préfixé par ``/api``)."""
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._base_url}{path}"

    def _headers(self, *, authenticated: bool = True) -> dict[str, str]:
        """Retourne les entêtes HTTP de base (auth optionnelle)."""
        headers = {"Accept": "application/json"}
        if authenticated and self._tokens.access_token:
            headers["Authorization"] = f"Bearer {self._tokens.access_token}"
        return headers

    def _handle(self, response: Response) -> Any:
        """Valide un statut 2xx et retourne le corps JSON (ou ``None`` sur 204)."""
        if response.status_code == 204:
            return None
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if not response.ok:
            detail = ""
            if isinstance(payload, dict):
                detail = str(payload.get("detail") or payload.get("error") or "")
            raise ApiError(response.status_code, detail or response.text)
        return payload

    def _request(
        self, method: str, path: str, *,
        json: Any | None = None, params: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None, data: dict[str, Any] | None = None,
        authenticated: bool = True, allow_refresh: bool = True,
        timeout: float | None = None,
    ) -> Any:
        """Effectue une requête et gère le rafraîchissement automatique."""
        response = self._session.request(
            method, self._url(path),
            headers=self._headers(authenticated=authenticated),
            json=json, params=params, files=files, data=data,
            timeout=timeout or self._timeout,
        )
        if (
            response.status_code == 401
            and allow_refresh
            and self._tokens.refresh_token
            and path != "/api/auth/refresh"
        ):
            self.refresh_access_token()
            response = self._session.request(
                method, self._url(path),
                headers=self._headers(authenticated=authenticated),
                json=json, params=params, files=files, data=data,
                timeout=timeout or self._timeout,
            )
        return self._handle(response)

    # ------------------------------------------------------------------ #
    # Auth
    # ------------------------------------------------------------------ #
    def health(self) -> dict[str, str]:
        """Ping l'API (endpoint public — utile pour vérifier l'URL)."""
        return self._request("GET", "/api/health", authenticated=False)

    def login(self, username: str, password: str) -> dict[str, Any]:
        """Authentifie un utilisateur et mémorise les tokens."""
        payload = self._request(
            "POST", "/api/auth/login",
            json={"username": username, "password": password},
            authenticated=False, allow_refresh=False,
        )
        self._tokens = Tokens(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            expires_in=int(payload.get("expires_in", 0)),
            user=payload.get("user", {}),
        )
        return dict(self._tokens.user)

    def refresh_access_token(self) -> None:
        """Rafraîchit le token d'accès à partir du refresh token."""
        payload = self._request(
            "POST", "/api/auth/refresh",
            json={"refresh_token": self._tokens.refresh_token},
            authenticated=False, allow_refresh=False,
        )
        self._tokens.access_token = payload["access_token"]
        self._tokens.expires_in = int(payload.get("expires_in", 0))

    def me(self) -> dict[str, Any]:
        """Retourne les infos de l'utilisateur courant."""
        return self._request("GET", "/api/auth/me")

    def logout(self) -> None:
        """Réinitialise la session locale (aucun endpoint serveur — JWT stateless)."""
        self._tokens = Tokens()

    # ------------------------------------------------------------------ #
    # Users (Admin)
    # ------------------------------------------------------------------ #
    def list_users(self) -> list[dict[str, Any]]:
        """Liste les utilisateurs (Admin uniquement côté serveur)."""
        return self._request("GET", "/api/users")

    def create_user(
        self, username: str, password: str, role: str, full_name: str = "",
    ) -> dict[str, Any]:
        """Crée un utilisateur (Admin uniquement)."""
        return self._request(
            "POST", "/api/users",
            json={"username": username, "password": password,
                  "role": role, "full_name": full_name},
        )

    def change_password(self, user_id: int, new_password: str) -> None:
        """Change le mot de passe d'un utilisateur (Admin ou soi-même)."""
        self._request(
            "POST", f"/api/users/{user_id}/password",
            json={"new_password": new_password},
        )

    def delete_user(self, user_id: int) -> None:
        """Supprime un utilisateur (Admin uniquement)."""
        self._request("DELETE", f"/api/users/{user_id}")

    # ------------------------------------------------------------------ #
    # Interventions
    # ------------------------------------------------------------------ #
    def list_interventions(
        self, *, search: str = "", autoroute: str = "", statut: str = "",
    ) -> list[dict[str, Any]]:
        """Liste les interventions avec filtres optionnels."""
        params = {k: v for k, v in {
            "search": search, "autoroute": autoroute, "statut": statut,
        }.items() if v}
        return self._request("GET", "/api/interventions", params=params)

    def create_intervention(self, data: dict[str, Any]) -> dict[str, Any]:
        """Crée une intervention (Admin ou Planificateur)."""
        return self._request("POST", "/api/interventions", json=data)

    def update_intervention(
        self, intervention_id: int, changes: dict[str, Any],
    ) -> dict[str, Any]:
        """Met à jour partiellement une intervention."""
        return self._request(
            "PATCH", f"/api/interventions/{intervention_id}", json=changes,
        )

    def delete_intervention(self, intervention_id: int) -> None:
        """Supprime une intervention."""
        self._request("DELETE", f"/api/interventions/{intervention_id}")

    # ------------------------------------------------------------------ #
    # Modules ASF (inspections / rapports / incidents / matériel)
    # ------------------------------------------------------------------ #
    def list_module(
        self, sheet: str, *, search: str = "",
    ) -> list[dict[str, Any]]:
        """Liste les lignes d'un module ASF."""
        params = {"search": search} if search else None
        return self._request("GET", f"/api/modules/{sheet}", params=params)

    def create_module_row(
        self, sheet: str, data: dict[str, Any],
    ) -> dict[str, Any]:
        """Ajoute une ligne dans un module."""
        return self._request("POST", f"/api/modules/{sheet}", json={"data": data})

    def update_module_row(
        self, sheet: str, row_id: int, data: dict[str, Any],
    ) -> dict[str, Any]:
        """Met à jour une ligne d'un module."""
        return self._request(
            "PATCH", f"/api/modules/{sheet}/{row_id}", json={"data": data},
        )

    def delete_module_row(self, sheet: str, row_id: int) -> None:
        """Supprime une ligne d'un module."""
        self._request("DELETE", f"/api/modules/{sheet}/{row_id}")

    # ------------------------------------------------------------------ #
    # Documents
    # ------------------------------------------------------------------ #
    def list_documents(
        self, *, entity: str = "", entity_id: str = "",
    ) -> list[dict[str, Any]]:
        """Liste les documents (filtres optionnels)."""
        params = {k: v for k, v in {
            "entity": entity, "entity_id": entity_id,
        }.items() if v}
        return self._request("GET", "/api/documents", params=params)

    def upload_document(
        self, entity: str, entity_id: str, file_path: Path, notes: str = "",
    ) -> dict[str, Any]:
        """Envoie un document à attacher à une entité (multipart)."""
        with Path(file_path).open("rb") as file:
            files = {"file": (file_path.name, file, "application/octet-stream")}
            data = {"entity": entity, "entity_id": entity_id, "notes": notes}
            return self._request(
                "POST", "/api/documents", files=files, data=data,
                timeout=_UPLOAD_TIMEOUT,
            )

    def download_document(self, document_id: int, destination: Path) -> Path:
        """Télécharge un document et retourne le chemin local."""
        response = self._session.get(
            self._url(f"/api/documents/{document_id}/download"),
            headers=self._headers(), stream=True, timeout=_UPLOAD_TIMEOUT,
        )
        if not response.ok:
            raise ApiError(response.status_code, response.text)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as fp:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    fp.write(chunk)
        return destination

    def delete_document(self, document_id: int) -> None:
        """Supprime un document."""
        self._request("DELETE", f"/api/documents/{document_id}")

    # ------------------------------------------------------------------ #
    # Audit
    # ------------------------------------------------------------------ #
    def list_audit(
        self, *, entity: str = "", search: str = "", limit: int = 300,
    ) -> list[dict[str, Any]]:
        """Retourne les entrées d'audit trail."""
        params: dict[str, Any] = {"limit": limit}
        if entity:
            params["entity"] = entity
        if search:
            params["search"] = search
        return self._request("GET", "/api/audit", params=params)

    # ------------------------------------------------------------------ #
    # Server-Sent Events (URL utilitaire pour le module ``sync``)
    # ------------------------------------------------------------------ #
    def sse_url(self) -> str:
        """Construit l'URL SSE authentifiée pour le listener temps réel."""
        return f"{self._base_url}/api/events?token={self._tokens.access_token}"
