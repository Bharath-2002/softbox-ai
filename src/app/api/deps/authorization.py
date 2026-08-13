"""Capability enforcement and identity extraction at the route boundary (D4).

``require_capability`` is the reusable part and has not changed since it was
first written — it only needs a ``Principal``, however one was obtained.
``get_current_principal`` is the piece that has: it now decodes the request's
bearer access token via the ``TokenIssuer`` port (M1 chunk 4 commit 3),
retiring the ``NotImplementedError`` placeholder that stood in its place
until real tokens existed to verify, and binds ``tenant_id`` to the logging
context once it is known (M1 chunk 5) — the request-id-only binding
``RequestContextMiddleware`` does happens before any principal exists, so
this is the earliest point in the request that can add it.

``require_tenant_context`` and ``require_platform_admin`` are the two
plane-enforcing dependencies attached at router level to ``admin`` and
``platform`` respectively (``api/routers/``) — every route mounted under
either router is gated by construction, not by remembering to add a check
per endpoint.

No database lookup here — the whole point of the access token is that its
claims (role, capabilities, platform-admin flag) were already resolved once,
at issuance (login or refresh). Trusting them again on every request is what
"stateless" means; if they go stale before the token's short expiry, that is
the accepted cost of not hitting the database on every single request.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.entities.capabilities import Capability
from app.entities.principal import Principal
from app.entities.roles import Role
from app.services.ports.token_issuer import TokenIssuer
from app.shared.clock import utcnow
from app.shared.errors import AuthenticationError, PermissionDeniedError
from app.shared.ids import TenantId, UserId
from app.shared.logging import bind_request_context

_bearer_scheme = HTTPBearer(auto_error=False)


def get_token_issuer(request: Request) -> TokenIssuer:
    """Reads the instance ``bootstrap`` attached to ``app.state`` — the same
    pattern as the database engine in ``bootstrap/app.py``. Never constructs
    one itself: that would mean importing ``infrastructure``, which this
    layer may not do."""
    issuer: TokenIssuer = request.app.state.token_issuer
    return issuer


async def get_current_principal(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    token_issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
) -> Principal:
    if credentials is None:
        raise AuthenticationError("Missing bearer token.")

    claims = token_issuer.decode(credentials.credentials, now=utcnow())

    principal = Principal(
        user_id=UserId(UUID(claims.subject)),
        tenant_id=TenantId(UUID(claims.tenant_id)) if claims.tenant_id else None,
        role=Role(claims.role) if claims.role else None,
        capabilities=frozenset(claims.capabilities),
        is_platform_admin=claims.is_platform_admin,
        impersonated_by=UserId(UUID(claims.impersonated_by)) if claims.impersonated_by else None,
    )
    if principal.tenant_id is not None:
        bind_request_context(tenant_id=str(principal.tenant_id))
    return principal


PrincipalDep = Annotated[Principal, Depends(get_current_principal)]


async def require_tenant_context(principal: PrincipalDep) -> Principal:
    """Gate for the ``admin`` router: authenticated, and acting within a
    bound tenant. A platform-scoped token (no active tenant) is a 403 here,
    not a 401 — it is authenticated, just the wrong plane for this route."""
    if principal.tenant_id is None:
        raise PermissionDeniedError("A tenant-scoped session is required.")
    return principal


async def require_platform_admin(principal: PrincipalDep) -> Principal:
    """Gate for the ``platform`` router (D4)."""
    principal.require_platform_admin()
    return principal


def require_capability(capability: Capability | str) -> Callable[[Principal], Awaitable[Principal]]:
    """A route dependency: ``Depends(require_capability(Capability.CATALOG_PUBLISH))``.

    Returns the principal so a route can use it further (audit logging the
    actor, for instance) without a second lookup.
    """

    async def dependency(principal: PrincipalDep) -> Principal:
        principal.require_capability(capability)
        return principal

    return dependency
