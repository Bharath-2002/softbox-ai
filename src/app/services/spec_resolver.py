"""D15's read path: "nothing reads the live slot tables except the spec
editor." Every other consumer — generation, a product pinning its spec at
creation, a regeneration years later — reads a category's spec through
here, never through ``attribute_definitions``/``variant_axes``/... directly.
"""

from __future__ import annotations

from typing import Any

from app.services.ports.category_spec_version_repository import CategorySpecVersionRepository
from app.shared.errors import NotFoundError
from app.shared.ids import CategoryId, TenantId


class SpecResolver:
    def __init__(self, category_spec_versions: CategorySpecVersionRepository) -> None:
        self._category_spec_versions = category_spec_versions

    async def resolve_published(
        self, tenant_id: TenantId, category_id: CategoryId, version: int
    ) -> dict[str, Any]:
        row = await self._category_spec_versions.get_by_version(tenant_id, category_id, version)
        if row is None:
            raise NotFoundError("Category spec version not found.")
        return row.snapshot
