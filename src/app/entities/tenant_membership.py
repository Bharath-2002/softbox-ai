"""A user's role within one tenant.

``extra_capabilities`` is a tenant-specific escape hatch — grants beyond what
the role implies, without inventing a new role for a one-off case. Resolving
role + extras into an allow/deny decision is the identity feature's job, not
this entity's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.entities.roles import Role
from app.shared.ids import TenantId, TenantMembershipId, UserId, new_tenant_membership_id


@dataclass
class TenantMembership:
    id: TenantMembershipId
    tenant_id: TenantId
    user_id: UserId
    role: Role
    extra_capabilities: list[str]
    created_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        user_id: UserId,
        *,
        role: Role,
        now: datetime,
        extra_capabilities: list[str] | None = None,
    ) -> TenantMembership:
        return TenantMembership(
            id=new_tenant_membership_id(),
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            extra_capabilities=extra_capabilities or [],
            created_at=now,
        )
