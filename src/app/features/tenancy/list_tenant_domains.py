"""Lists a tenant's own registered domains. Unbounded like
``ListCategoryChildren`` — an admin-configured handful of hostnames, not an
open-ended, user-generated collection."""

from __future__ import annotations

from app.entities.tenant_domain import TenantDomain
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import TenantId


class ListTenantDomains:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, tenant_id: TenantId) -> list[TenantDomain]:
        async with self._uow_factory(tenant_id) as uow:
            return await uow.tenant_domains.list_for_tenant(tenant_id)
