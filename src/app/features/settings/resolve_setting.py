"""Thin transactional wrapper around ``SettingsResolver.resolve`` (D16) —
the read-only counterpart to ``UpsertSetting``, kept as its own ``features``
use case so every HTTP-reachable read opens one unit of work, the same
shape as ``GetPublishedCategorySpec``.
"""

from __future__ import annotations

from typing import Any

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.settings_resolver import SettingsResolver
from app.shared.ids import CategoryId, ProductId, TenantId


class ResolveSetting:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        key: str,
        category_id: CategoryId | None = None,
        product_id: ProductId | None = None,
    ) -> Any | None:
        async with self._uow_factory(tenant_id) as uow:
            resolver = SettingsResolver(uow.settings, uow.categories)
            return await resolver.resolve(
                tenant_id, key, category_id=category_id, product_id=product_id
            )
