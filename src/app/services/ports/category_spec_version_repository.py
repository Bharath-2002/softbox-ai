"""Immutable published-spec snapshot storage (D15). Tenant id is explicit on
every method.

Deliberately no ``update`` method — this is the enforcement mechanism for
D15's immutability guarantee, not a convention a caller could violate by
mistake. Once a version publishes, no code path in this codebase can express
changing its ``snapshot``. ``services.attribute_model_compiler.AttributeModelCache``
depends on exactly this property.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.category_spec_version import CategorySpecVersion
from app.shared.ids import CategoryId, CategorySpecVersionId, TenantId


class CategorySpecVersionRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, version_id: CategorySpecVersionId
    ) -> CategorySpecVersion | None: ...

    async def get_by_version(
        self, tenant_id: TenantId, category_id: CategoryId, version: int
    ) -> CategorySpecVersion | None:
        """What ``SpecResolver`` calls — the one path everything outside the
        spec editor uses to read a category's spec (D15)."""
        ...

    async def add(self, version: CategorySpecVersion) -> None: ...

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[CategorySpecVersion]:
        """Every published version of one category, newest first — the
        publish-history view."""
        ...
