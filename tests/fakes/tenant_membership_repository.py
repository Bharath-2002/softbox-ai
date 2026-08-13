from __future__ import annotations

from app.entities.tenant_membership import TenantMembership
from app.shared.ids import TenantId, UserId


class InMemoryTenantMembershipRepository:
    def __init__(self) -> None:
        # Keyed by (tenant_id, user_id) - the real unique constraint - not by
        # id alone, so a fake test double cannot accidentally permit two
        # memberships for the same user in the same tenant.
        self._rows: dict[tuple[TenantId, UserId], TenantMembership] = {}

    async def get(self, tenant_id: TenantId, user_id: UserId) -> TenantMembership | None:
        return self._rows.get((tenant_id, user_id))

    async def list_for_user(self, user_id: UserId) -> list[TenantMembership]:
        return [m for m in self._rows.values() if m.user_id == user_id]

    async def add(self, membership: TenantMembership) -> None:
        self._rows[(membership.tenant_id, membership.user_id)] = membership
