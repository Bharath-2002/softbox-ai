"""Resolves a storefront request's tenant from its Host header (D4, M8).

The one caller in this codebase allowed to open a unit of work with
``tenant_id=None`` outside a login/platform-plane flow — there is, by
definition, no tenant to bind yet. Returns ``None`` for an unknown hostname
rather than raising; the api-layer dependency that calls this decides that
is a 404, per ``NotFoundError``'s own "do not distinguish missing from
someone else's" reasoning applied one level up.
"""

from __future__ import annotations

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import TenantId


class ResolveTenantFromHost:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(self, *, hostname: str) -> TenantId | None:
        async with self._uow_factory(None) as uow:
            domain = await uow.tenant_domains.resolve_by_hostname(hostname)
            return domain.tenant_id if domain is not None else None
