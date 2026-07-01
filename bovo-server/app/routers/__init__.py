"""Package des routeurs REST de Bovo ASF Manager Server."""

from app.routers import audit, auth, documents, events, interventions, modules, users

__all__ = ["audit", "auth", "documents", "events", "interventions", "modules", "users"]
