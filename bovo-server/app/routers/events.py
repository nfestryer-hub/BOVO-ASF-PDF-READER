"""Router : Server-Sent Events (SSE) pour la synchronisation temps réel."""

from __future__ import annotations

import asyncio
from typing import Annotated, Any

import jwt
from fastapi import APIRouter, HTTPException, Query, Request, status
from sse_starlette.sse import EventSourceResponse

from app.events import broadcaster, keepalive_seconds
from app.security import decode_token

router = APIRouter(prefix="/api/events", tags=["events"])


def _authenticate(token: str | None) -> dict[str, Any]:
    """Vérifie le token JWT passé en paramètre de requête (SSE ne permet pas
    d'entête ``Authorization`` en navigateur natif)."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token requis dans le paramètre ``token``.",
        )
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide.",
        ) from exc
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Type de token invalide.",
        )
    return payload


@router.get("")
async def sse_stream(
    request: Request,
    token: Annotated[str, Query()] = "",
) -> EventSourceResponse:
    """Flux SSE : diffuse chaque modification métier aux clients connectés.

    Le client doit passer son ``access_token`` en query-string, car les
    navigateurs ne permettent pas d'entête ``Authorization`` sur EventSource.
    Le token est vérifié à l'ouverture ; il n'est pas revalidé ensuite
    (déconnexion à l'expiration du refresh côté client).
    """
    _authenticate(token)
    queue = await broadcaster.subscribe()

    async def event_publisher():
        try:
            # Handshake initial pour signaler la connexion établie.
            yield {"event": "ready", "data": "connected"}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    message = await asyncio.wait_for(
                        queue.get(), timeout=keepalive_seconds(),
                    )
                    yield {"event": "change", "data": message}
                except asyncio.TimeoutError:
                    # Keep-alive : commentaire SSE ignoré par les clients.
                    yield {"event": "ping", "data": "keepalive"}
        finally:
            await broadcaster.unsubscribe(queue)

    return EventSourceResponse(event_publisher())
