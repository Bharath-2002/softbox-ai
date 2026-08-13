from __future__ import annotations

import pytest

from app.entities.category_spec_version import CategorySpecVersion
from app.services.spec_resolver import SpecResolver
from app.shared.clock import utcnow
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id, new_user_id
from tests.fakes.category_spec_version_repository import InMemoryCategorySpecVersionRepository


async def test_resolve_published_returns_the_stored_snapshot() -> None:
    versions = InMemoryCategorySpecVersionRepository()
    resolver = SpecResolver(versions)
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    snapshot = {"attribute_definitions": [{"key": "fabric"}]}
    version = CategorySpecVersion.create(
        tenant_id,
        category_id,
        version=3,
        snapshot=snapshot,
        published_by=new_user_id(),
        now=utcnow(),
    )
    await versions.add(version)

    resolved = await resolver.resolve_published(tenant_id, category_id, 3)

    assert resolved == snapshot


async def test_resolve_published_raises_not_found_for_an_unknown_version() -> None:
    resolver = SpecResolver(InMemoryCategorySpecVersionRepository())

    with pytest.raises(NotFoundError):
        await resolver.resolve_published(new_tenant_id(), new_category_id(), 1)
