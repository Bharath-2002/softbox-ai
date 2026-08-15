"""Storefront tenant resolution (D4). ``resolve_by_hostname`` is the one
method a caller with no tenant bound yet may call — it exists precisely to
establish which tenant a request belongs to, so it cannot itself take a
``tenant_id``. Every other method is an ordinary tenant-scoped operation for
managing a tenant's own domains.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.tenant_domain import TenantDomain
from app.shared.ids import TenantDomainId, TenantId


class TenantDomainRepository(Protocol):
    async def resolve_by_hostname(self, hostname: str) -> TenantDomain | None: ...

    async def get(self, tenant_id: TenantId, domain_id: TenantDomainId) -> TenantDomain | None: ...

    async def list_for_tenant(self, tenant_id: TenantId) -> list[TenantDomain]: ...

    async def add(self, domain: TenantDomain) -> None: ...
