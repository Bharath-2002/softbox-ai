"""Composition root — builds the application and wires adapters to ports.

This is the only module permitted to import ``app.infrastructure``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api import health
from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.bootstrap.settings import Settings, get_settings
from app.infrastructure.observability.logging import configure_logging
from app.infrastructure.persistence.database import create_engine, create_session_factory, ping
from app.shared.logging import get_logger

_log = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    _log.info("application_starting", environment=settings.environment)
    yield
    _log.info("application_stopping")
    await app.state.db_engine.dispose()
    _log.info("application_stopped")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Accepts settings so a test can construct an app against a different
    configuration without touching the environment or the settings cache.
    """
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, fmt=settings.log_format)

    app = FastAPI(
        title="Softbox AI",
        version="0.1.0",
        # Interactive docs are useful in development and an attack surface in
        # production, where the OpenAPI schema is published deliberately instead.
        docs_url=None if settings.is_production else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/openapi.json",
        lifespan=_lifespan,
    )
    app.state.settings = settings

    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    register_exception_handlers(app)

    # The app connects as the non-owner role (D3) — SOFTBOX_DATABASE_URL, never
    # the owner DSN migrations use. See scripts/bootstrap_local_db.sh.
    engine = create_engine(
        settings.database_url.get_secret_value(),
        echo=settings.database_echo,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )
    app.state.db_engine = engine
    app.state.db_session_factory = create_session_factory(engine)
    health.register_readiness_check(app, "database", lambda: ping(engine))

    # Ops endpoints sit outside the versioned prefix: probes should not have to
    # follow an API version bump.
    app.include_router(health.router)

    return app
