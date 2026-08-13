"""Resolves who a user is for one request (D4).

The I/O-bound counterpart to ``entities.roles.ROLE_CAPABILITIES``: that table
says what a role means in the abstract, this asks the repositories what role
(if any) this specific user actually holds and builds the ``Principal`` a
capability check runs against.

Resolution always succeeds — a user with no membership in the requested
tenant gets a ``Principal`` with ``role=None`` and no capabilities, not an
error. Denial is `Principal.require_capability`'s job, at the point where a
specific action is attempted; a resolver that raised instead would conflate
"you don't have this specific permission" with "something went wrong."
"""

from __future__ import annotations

from app.entities.principal import Principal
from app.entities.roles import ROLE_CAPABILITIES
from app.services.ports.platform_admin_repository import PlatformAdminRepository
from app.services.ports.tenant_membership_repository import TenantMembershipRepository
from app.shared.ids import TenantId, UserId


class PrincipalResolver:
    def __init__(
        self,
        memberships: TenantMembershipRepository,
        platform_admins: PlatformAdminRepository,
    ) -> None:
        self._memberships = memberships
        self._platform_admins = platform_admins

    async def resolve(self, user_id: UserId, tenant_id: TenantId | None) -> Principal:
        is_platform_admin = await self._platform_admins.is_admin(user_id)

        if tenant_id is None:
            return Principal(
                user_id=user_id,
                tenant_id=None,
                role=None,
                capabilities=frozenset(),
                is_platform_admin=is_platform_admin,
            )

        membership = await self._memberships.get(tenant_id, user_id)
        if membership is None:
            # Not a member of this tenant - including a platform admin with
            # no explicit membership. See the module and Principal docstrings
            # for why that is not treated as sufficient on its own.
            return Principal(
                user_id=user_id,
                tenant_id=tenant_id,
                role=None,
                capabilities=frozenset(),
                is_platform_admin=is_platform_admin,
            )

        base = {str(c) for c in ROLE_CAPABILITIES.get(membership.role, frozenset())}
        capabilities = base | set(membership.extra_capabilities)
        return Principal(
            user_id=user_id,
            tenant_id=tenant_id,
            role=membership.role,
            capabilities=frozenset(capabilities),
            is_platform_admin=is_platform_admin,
        )
