"""DI provider functions (CLAUDE.md §4): return **port types**, not concrete
classes, so a route depends on an interface and a test can override with a
fake via ``app.dependency_overrides``.

Everything here reads from ``app.state`` (built once in
``bootstrap.app.create_app``), the same pattern ``api/deps/*`` uses for
infrastructure ports — the difference is these construct **use cases**
(``features`` layer), which need both ports and config (like
``admin_emails``), so they belong in ``bootstrap`` (the only layer allowed
to see both ``features`` and ``infrastructure``) rather than ``api``.

This is the first module in this package — no route needed a use case
before ``/auth/*``, which chunk 4 explicitly deferred until routers existed
at all.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.api.deps.authorization import get_token_issuer
from app.features.identity.complete_login import CompleteLogin
from app.features.identity.logout import Logout
from app.features.identity.refresh_session import RefreshSession
from app.services.ports.identity_provider import IdentityProvider
from app.services.ports.token_issuer import TokenIssuer
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock


def get_uow_factory(request: Request) -> UnitOfWorkFactory:
    factory: UnitOfWorkFactory = request.app.state.uow_factory
    return factory


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_google_identity_provider(request: Request) -> IdentityProvider:
    provider: IdentityProvider = request.app.state.google_identity_provider
    return provider


UowFactoryDep = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
ClockDep = Annotated[Clock, Depends(get_clock)]
GoogleIdentityProviderDep = Annotated[IdentityProvider, Depends(get_google_identity_provider)]


def get_complete_login(
    request: Request,
    provider: GoogleIdentityProviderDep,
    token_issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
    uow_factory: UowFactoryDep,
    clock: ClockDep,
) -> CompleteLogin:
    admin_emails = frozenset(request.app.state.settings.admin_emails)
    return CompleteLogin(
        provider, token_issuer, uow_factory, clock, bootstrap_admin_emails=admin_emails
    )


def get_refresh_session(
    token_issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
    uow_factory: UowFactoryDep,
    clock: ClockDep,
) -> RefreshSession:
    return RefreshSession(token_issuer, uow_factory, clock)


def get_logout(uow_factory: UowFactoryDep, clock: ClockDep) -> Logout:
    return Logout(uow_factory, clock)


CompleteLoginDep = Annotated[CompleteLogin, Depends(get_complete_login)]
RefreshSessionDep = Annotated[RefreshSession, Depends(get_refresh_session)]
LogoutDep = Annotated[Logout, Depends(get_logout)]
