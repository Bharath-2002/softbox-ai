"""Thin transactional wrapper around ``SpecResolver.resolve_published`` (D15)
— the read-only counterpart to ``PublishCategorySpec``, kept as its own
``features`` use case rather than called directly from a router, so every
HTTP-reachable read goes through the same "open one unit of work" shape as
every write.
"""

from __future__ import annotations

from typing import Any

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.spec_resolver import SpecResolver
from app.shared.ids import CategoryId, TenantId


class GetPublishedCategorySpec:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self, *, tenant_id: TenantId, category_id: CategoryId, version: int
    ) -> dict[str, Any]:
        async with self._uow_factory(tenant_id) as uow:
            resolver = SpecResolver(uow.category_spec_versions)
            return await resolver.resolve_published(tenant_id, category_id, version)
