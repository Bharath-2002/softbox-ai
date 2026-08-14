from __future__ import annotations

from app.shared.ids import TenantId


class InMemoryTenantRepository:
    """Seeded directly by tests via ``active_tenant_ids`` — there is no
    ``add`` method on the port to call instead (see its module docstring for
    why: full tenant CRUD is out of scope until M9)."""

    def __init__(self, active_tenant_ids: list[TenantId] | None = None) -> None:
        self.active_tenant_ids = list(active_tenant_ids or [])

    async def list_active(self) -> list[TenantId]:
        return list(self.active_tenant_ids)
