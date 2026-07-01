"""Broadcaster d'événements Server-Sent Events (SSE).

Chaque client desktop qui souhaite recevoir les modifications temps-réel se
connecte à ``GET /api/events`` (avec son token JWT). Le broadcaster maintient
la liste des files d'attente et diffuse chaque modification métier vers tous
les clients connectés. Un ping périodique garde la connexion vivante à
travers les proxies.

Les événements ont la forme JSON :
::

    {
        "entity": "intervention" | "module.inspections" | "user" | "document",
        "action": "create" | "update" | "delete",
        "id":     <str>,
        "by":     <username>,
        "at":     <ISO-8601 UTC>,
    }
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from app.config import get_settings


class EventBroadcaster:
    """Diffuse les événements de modification vers les clients SSE."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._lock = asyncio.Lock()
        self._main_loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Enregistre la loop principale (appelé au démarrage FastAPI).

        Les endpoints ``def`` synchrones tournent dans un threadpool et ne
        disposent pas de leur propre loop. On mémorise la loop principale
        pour permettre à :func:`publish_sync` de programmer les diffusions.
        """
        self._main_loop = loop

    async def subscribe(self) -> asyncio.Queue[str]:
        """Enregistre un nouvel abonné et retourne sa file d'événements."""
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=200)
        async with self._lock:
            self._subscribers.add(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        """Retire un abonné et vide sa file."""
        async with self._lock:
            self._subscribers.discard(queue)

    async def publish(
        self, *, entity: str, action: str, entity_id: str,
        by: str = "", extra: dict[str, Any] | None = None,
    ) -> None:
        """Diffuse un événement à tous les abonnés (best-effort, non bloquant)."""
        payload = {
            "entity": entity, "action": action, "id": entity_id,
            "by": by, "at": datetime.now(UTC).isoformat(),
        }
        if extra:
            payload.update(extra)
        message = json.dumps(payload, ensure_ascii=False, default=str)
        async with self._lock:
            targets = list(self._subscribers)
        for queue in targets:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                continue


broadcaster = EventBroadcaster()


def publish_sync(**kwargs: Any) -> None:
    """Publie un événement depuis un contexte synchrone (endpoint ``def``).

    Utilise :meth:`asyncio.AbstractEventLoop.call_soon_threadsafe` pour
    programmer la diffusion dans la loop principale enregistrée par
    :func:`EventBroadcaster.bind_loop` (au démarrage). Sans échec si aucune
    loop n'est encore liée (tests unitaires hors FastAPI).
    """
    loop = broadcaster._main_loop  # noqa: SLF001 — helper interne
    if loop is None:
        return
    asyncio.run_coroutine_threadsafe(broadcaster.publish(**kwargs), loop)


def keepalive_seconds() -> int:
    """Fréquence des pings SSE en secondes."""
    _ = get_settings()  # respect l'ordre d'init de config
    return 20
