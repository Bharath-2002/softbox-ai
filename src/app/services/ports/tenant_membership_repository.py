"""Tenant-scoped: every method takes ``tenant_id`` explicitly (D3), except the
one query that is structurally "which tenants does this user belong to at
all" and so cannot be scoped by a single tenant.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.tenant_membership import TenantMembership
from app.shared.ids import TenantId, UserId


class TenantMembershipRepository(Protocol):
    async def get(self, tenant_id: TenantId, user_id: UserId) -> TenantMembership | None: ...

    async def list_for_user(self, user_id: UserId) -> list[TenantMembership]:
        """Every tenant this user belongs to, across tenants — the tenant
        switcher and the login flow's "which tenant did you mean" step both
        need this, and neither has a tenant to scope by yet."""
        ...

    async def add(self, membership: TenantMembership) -> None: ...
