from __future__ import annotations

from app.entities.tenant_domain import TenantDomain
from app.shared.ids import TenantDomainId, TenantId


class InMemoryTenantDomainRepository:
    def __init__(self) -> None:
        self._rows: dict[TenantDomainId, TenantDomain] = {}

    async def resolve_by_hostname(self, hostname: str) -> TenantDomain | None:
        for row in self._rows.values():
            if row.hostname == hostname:
                return row
        return None

    async def get(self, tenant_id: TenantId, domain_id: TenantDomainId) -> TenantDomain | None:
        row = self._rows.get(domain_id)
        if row is None or row.tenant_id != tenant_id:
            return None
        return row

    async def list_for_tenant(self, tenant_id: TenantId) -> list[TenantDomain]:
        return sorted(
            (row for row in self._rows.values() if row.tenant_id == tenant_id),
            key=lambda row: row.created_at,
        )

    async def add(self, domain: TenantDomain) -> None:
        self._rows[domain.id] = domain
