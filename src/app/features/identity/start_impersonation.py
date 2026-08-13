"""Issues a short-lived, audited access token letting a platform admin act
as a specific tenant member, for support purposes (D4).

Time-boxed by construction, not a separate mechanism: this mints exactly
one access token via the same ``TokenIssuer`` every other login path uses
(its existing short TTL — 15 minutes by default), and deliberately issues
**no refresh token**. When it expires, resuming requires going through this
same audited path again, not silently extending an old grant.

Requires the caller to already be a verified platform admin — that check is
the route's job (``require_platform_admin``, attached at router level to
``platform.router``), not this use case's. This use case trusts the
``admin_user_id`` it is given and focuses on what it alone is responsible
for: confirming the target actually holds a role in the target tenant, and
writing the audit trail before any token is issued.

The issued token always carries ``is_platform_admin=False``, regardless of
whether the real admin has that flag — impersonation grants the target's
own standing, never the admin's platform-wide power layered on top of it
(see ``Principal``'s and ``AccessTokenClaims.impersonated_by``'s
docstrings).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.entities.roles import ROLE_CAPABILITIES
from app.services.ports.token_issuer import AccessTokenClaims, TokenIssuer
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import TenantId, UserId


@dataclass(frozen=True)
class ImpersonationResult:
    access_token: str


class StartImpersonation:
    def __init__(
        self, token_issuer: TokenIssuer, uow_factory: UnitOfWorkFactory, clock: Clock
    ) -> None:
        self._token_issuer = token_issuer
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        admin_user_id: UserId,
        target_user_id: UserId,
        target_tenant_id: TenantId,
        reason: str,
    ) -> ImpersonationResult:
        now = self._clock.now()

        async with self._uow_factory(target_tenant_id) as uow:
            membership = await uow.tenant_memberships.get(target_tenant_id, target_user_id)
            if membership is None:
                raise NotFoundError("Target user is not a member of the target tenant.")

            await uow.audit_log.record(
                target_tenant_id,
                actor_user_id=admin_user_id,
                action="impersonation.started",
                subject_type="user",
                subject_id=target_user_id,
                after={"reason": reason},
                now=now,
            )

            capabilities = {str(c) for c in ROLE_CAPABILITIES.get(membership.role, frozenset())}
            capabilities |= set(membership.extra_capabilities)

        access_token = self._token_issuer.encode(
            AccessTokenClaims(
                subject=str(target_user_id),
                tenant_id=str(target_tenant_id),
                role=membership.role.value,
                capabilities=sorted(capabilities),
                is_platform_admin=False,
                impersonated_by=str(admin_user_id),
            ),
            now=now,
        )
        return ImpersonationResult(access_token=access_token)
