"""Point d'entrée FastAPI de Bovo ASF Manager Server.

Séquence de démarrage :

1. Charge la configuration (``.env`` ou variables d'environnement).
2. Crée les tables PostgreSQL si nécessaire (SQLAlchemy ``create_all``).
3. Seede l'utilisateur Admin (idempotent).
4. Enregistre les routeurs REST + SSE.

Le serveur s'exécute derrière un reverse proxy (nginx/traefik) et écoute
sur le port ``8000`` (voir ``docker-compose.yml``).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.routers import audit, auth, documents, events, interventions, modules, users
from app.seed import seed_admin

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("bovo.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Init : crée les tables, seede l'admin, capture la loop asyncio."""
    import asyncio

    from app.events import broadcaster
    from app.models import Role
    from sqlalchemy import text

    broadcaster.bind_loop(asyncio.get_running_loop())
    logger.info("Initialisation du schéma PostgreSQL…")
    Base.metadata.create_all(bind=engine)
    # ------------------------------------------------------------------ #
    # Migration V1.2 : ajoute les valeurs manquantes de l'enum ``role``
    # (par ex. ``Inspecteur ITV`` introduite en V1.2). ``ALTER TYPE ADD
    # VALUE`` est idempotent grâce à ``IF NOT EXISTS`` (Postgres ≥ 9.6).
    # ------------------------------------------------------------------ #
    with engine.connect() as conn:
        for role in Role:
            try:
                conn.execute(text(
                    f"ALTER TYPE role ADD VALUE IF NOT EXISTS '{role.value}'"
                ))
                conn.commit()
            except Exception as exc:  # noqa: BLE001 - migration best-effort
                logger.warning("Migration enum role '%s' : %s", role.value, exc)
                conn.rollback()
    with SessionLocal() as session:
        seed_admin(session)
    logger.info("Serveur prêt (Bovo ASF Manager v%s).", __version__)
    yield


app = FastAPI(
    title="Bovo ASF Manager API",
    description=(
        "API REST centralisée du logiciel Bovo ASF Manager : authentification "
        "JWT, interventions, inspections ASF, documents, audit trail et flux "
        "temps-réel via Server-Sent Events."
    ),
    version=__version__,
    lifespan=lifespan,
)

settings = get_settings()
origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(interventions.router)
app.include_router(modules.router)
app.include_router(documents.router)
app.include_router(audit.router)
app.include_router(events.router)


@app.get("/api/health")
def healthcheck() -> dict[str, str]:
    """Endpoint de sonde de santé (utilisé par le reverse proxy et Docker)."""
    return {"status": "ok", "version": __version__}
