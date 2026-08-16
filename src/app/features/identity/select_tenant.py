"""Sets a session's active tenant and issues a token scoped to it (D4).

``CompleteLogin`` deliberately issues every new session with ``tenant_id
= None`` ("tenant selection is a separate concern, not built here" — that
module's own docstring). This is that separate concern: the one place a
session's ``tenant_id`` is ever set to something other than ``None``.

Same refresh-token-presented, lookup-by-hash, rotate-on-use shape
``RefreshSession`` already established — selecting a tenant is, mechanically,
a refresh that also changes what tenant the new token is scoped to. Rotating
the refresh token here too (not just the access token) means a stale
previously-issued refresh token cannot be replayed later to silently select
a different tenant than the one currently in use.

Requires an existing ``TenantMembership`` in the requested tenant —
``PermissionDeniedError``, not ``NotFoundError``: the caller is already an
authenticated, verified person, just not one with any standing in this
particular tenant (the same "authenticated, wrong plane" reasoning
``require_tenant_context`` already uses at the router layer). Whether the
tenant id itself is unknown or simply not theirs is not distinguished, for
the same reason ``NotFoundError`` itself does not distinguish "missing" from
"someone else's" — a membership lookup keyed on ``(tenant_id, user_id)``
cannot tell those apart anyway.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.ports.token_issuer import AccessTokenClaims, TokenIssuer
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.principal_resolver import PrincipalResolver
from app.shared.clock import Clock
from app.shared.errors import AuthenticationError, PermissionDeniedError
from app.shared.ids import TenantId
from app.shared.tokens import generate_token, hash_token


@dataclass(frozen=True)
class SelectTenantResult:
    access_token: str
    refresh_token: str


class SelectTenant:
    def __init__(
        self,
        token_issuer: TokenIssuer,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._token_issuer = token_issuer
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, refresh_token: str, tenant_id: TenantId) -> SelectTenantResult:
        presented_hash = hash_token(refresh_token)
        now = self._clock.now()

        async with self._uow_factory(None) as uow:
            session = await uow.sessions.get_by_refresh_token_hash(presented_hash)

            if session is None:
                reused = await uow.sessions.get_by_previous_token_hash(presented_hash)
                if reused is not None:
                    await uow.sessions.revoke_all_for_user(reused.user_id, now=now)
                raise AuthenticationError("Invalid refresh token.")

            if not session.is_active(now=now):
                raise AuthenticationError("Session is no longer active.")

            membership = await uow.tenant_memberships.get(tenant_id, session.user_id)
            if membership is None:
                raise PermissionDeniedError("Not a member of this tenant.")

            new_refresh_token = generate_token()
            session.previous_token_hash = session.refresh_token_hash
            session.refresh_token_hash = hash_token(new_refresh_token)
            session.tenant_id = tenant_id
            await uow.sessions.update(session)

            principal = await PrincipalResolver(
                uow.tenant_memberships, uow.platform_admins
            ).resolve(session.user_id, tenant_id)

        access_token = self._token_issuer.encode(
            AccessTokenClaims(
                subject=str(session.user_id),
                tenant_id=str(tenant_id),
                role=principal.role.value if principal.role else None,
                capabilities=sorted(principal.capabilities),
                is_platform_admin=principal.is_platform_admin,
            ),
            now=now,
        )
        return SelectTenantResult(access_token=access_token, refresh_token=new_refresh_token)
