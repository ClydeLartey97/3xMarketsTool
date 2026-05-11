from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.routes import public_router, router
from app.core.config import get_settings
from app.core.observability import configure_logging, instrument_app
from app.core.rate_limit import configure_rate_limiting
from app.db.compat import apply_sqlite_compat_migrations
from app.db.schema import database_has_schema
from app.db.session import SessionLocal, engine
from app.ingestion.seeds import seed_database

settings = get_settings()
configure_logging(settings)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    schema_ready = database_has_schema(engine)
    if schema_ready:
        apply_sqlite_compat_migrations(engine)
        with SessionLocal() as db:
            seed_database(db)
    else:
        logger.warning(
            "Database schema is not initialized. Run `alembic -c alembic.ini upgrade head`; "
            "startup seeding is disabled."
        )

    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
configure_rate_limiting(app)
app.include_router(public_router, prefix=settings.api_v1_prefix)
app.include_router(auth_router, prefix=settings.api_v1_prefix)
app.include_router(router, prefix=settings.api_v1_prefix)
instrument_app(app, engine, settings)
