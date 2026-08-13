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
from app.api.routers import admin, auth, platform, public, webhooks
from app.bootstrap.settings import Settings, get_settings
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.infrastructure.auth.oidc_provider import AuthlibIdentityProvider
from app.infrastructure.email.console_sender import ConsoleEmailSender
from app.infrastructure.email.smtp_sender import SmtpEmailSender
from app.infrastructure.observability.logging import configure_logging
from app.infrastructure.persistence.database import create_engine, create_session_factory, ping
from app.infrastructure.persistence.rate_limiter import SqlRateLimiter
from app.infrastructure.persistence.unit_of_work import make_unit_of_work_factory
from app.shared.clock import SystemClock
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

    # Read by app.bootstrap.di - the use-case-constructing dependencies for
    # /auth/* need both, and building repositories per-request calls for a
    # UnitOfWorkFactory (one transaction per use case call), not a shared
    # UnitOfWork instance.
    app.state.uow_factory = make_unit_of_work_factory(app.state.db_session_factory)
    app.state.clock = SystemClock()

    # Read by app.api.deps.authorization.get_token_issuer - the api layer may
    # not import infrastructure directly, so this is constructed here and
    # attached to app.state, the same pattern as the database engine above.
    app.state.token_issuer = AccessTokenCodec(settings.access_token_signing_key.get_secret_value())

    # Read by app.api.deps.rate_limit.get_rate_limiter - same pattern.
    app.state.rate_limiter = SqlRateLimiter(app.state.db_session_factory)

    # Read by app.api.deps.email.get_email_sender - same pattern. "console"
    # (the default) never touches a real SMTP relay - see ConsoleEmailSender.
    if settings.email_backend == "smtp":
        app.state.email_sender = SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user,
            password=settings.smtp_password.get_secret_value(),
            sender=settings.email_from,
        )
    else:
        app.state.email_sender = ConsoleEmailSender()

    # Read by app.bootstrap.di.get_google_identity_provider. Constructing
    # this never makes a network call (Authlib's OAuth().register() only
    # stores config; load_server_metadata is fetched lazily on first real
    # use) - safe to always build, even with an empty google_client_id in
    # local/test/CI where Google SSO is not configured.
    app.state.google_identity_provider = AuthlibIdentityProvider(
        provider_name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret.get_secret_value(),
        server_metadata_url=settings.google_discovery_url,
    )

    # Ops endpoints sit outside the versioned prefix: probes should not have to
    # follow an API version bump.
    app.include_router(health.router)

    # The four planes (CLAUDE.md §9), plus `auth` - a fifth, deliberate
    # addition (see app/api/routers/auth.py's module docstring and
    # docs/ARCHITECTURE.md's router table). Each carries its own auth
    # posture at router level (see app/api/routers/) - none of that lives
    # here.
    for router in (platform.router, admin.router, public.router, webhooks.router, auth.router):
        app.include_router(router, prefix=settings.api_prefix)

    return app
