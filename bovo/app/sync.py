"""Listener Server-Sent Events du client Bovo ASF Manager.

Ouvre une connexion SSE au serveur en arrière-plan et invoque une
callback à chaque événement métier reçu. Utilise ``sseclient-py`` pour
parser proprement le flux, et reconnecte automatiquement en cas de coupure.

Utilisation typique dans la GUI CustomTkinter::

    def on_event(payload: dict[str, Any]) -> None:
        # Ex. rafraîchir la table concernée.
        app.after(0, app.refresh_from_event, payload)

    listener = SseListener(client, on_event)
    listener.start()
    ...  # à la fermeture :
    listener.stop()
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

import requests
from sseclient import SSEClient

from app.api_client import ApiClient

logger = logging.getLogger("bovo.sync")

EventHandler = Callable[[dict[str, Any]], None]


class SseListener:
    """Écouteur SSE robuste et thread-safe pour le client Bovo ASF Manager."""

    _RECONNECT_INITIAL_DELAY = 2.0
    _RECONNECT_MAX_DELAY = 60.0
    _READ_TIMEOUT = 40.0

    def __init__(self, client: ApiClient, on_event: EventHandler) -> None:
        self._client = client
        self._on_event = on_event
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ #
    # Cycle de vie
    # ------------------------------------------------------------------ #
    def start(self) -> None:
        """Démarre la boucle SSE dans un thread daemon."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="BovoSse", daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Arrête proprement le listener."""
        self._stop.set()

    # ------------------------------------------------------------------ #
    # Boucle interne
    # ------------------------------------------------------------------ #
    def _loop(self) -> None:
        """Boucle principale avec reconnexion exponentielle."""
        delay = self._RECONNECT_INITIAL_DELAY
        while not self._stop.is_set():
            try:
                self._stream_once()
                delay = self._RECONNECT_INITIAL_DELAY  # reset après succès.
            except (requests.exceptions.RequestException, ValueError) as exc:
                logger.warning("SSE déconnecté (%s). Reconnexion dans %.1fs.",
                               exc, delay)
                if self._stop.wait(delay):
                    return
                delay = min(delay * 2, self._RECONNECT_MAX_DELAY)

    def _stream_once(self) -> None:
        """Ouvre un flux SSE et itère jusqu'à déconnexion."""
        url = self._client.sse_url()
        response = requests.get(
            url, stream=True, timeout=(10.0, self._READ_TIMEOUT),
            headers={"Accept": "text/event-stream"},
        )
        response.raise_for_status()
        events = SSEClient(response).events()  # type: ignore[arg-type]
        for event in events:
            if self._stop.is_set():
                return
            if event.event == "change" and event.data:
                try:
                    payload = json.loads(event.data)
                except json.JSONDecodeError:
                    continue
                try:
                    self._on_event(payload)
                except Exception:  # noqa: BLE001 - le handler ne doit pas crasher la loop.
                    logger.exception("Handler SSE : erreur non gérée.")
