from __future__ import annotations

import pytest

from app.entities.category_spec_version import CategorySpecVersion
from app.features.taxonomy.get_published_category_spec import GetPublishedCategorySpec
from app.shared.clock import utcnow
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id, new_user_id
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


async def test_returns_the_stored_snapshot() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = GetPublishedCategorySpec(uow_factory)
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    snapshot = {"attribute_definitions": [{"key": "fabric"}]}
    await uow_factory.category_spec_versions.add(
        CategorySpecVersion.create(
            tenant_id,
            category_id,
            version=1,
            snapshot=snapshot,
            published_by=new_user_id(),
            now=utcnow(),
        )
    )

    resolved = await use_case(tenant_id=tenant_id, category_id=category_id, version=1)

    assert resolved == snapshot


async def test_unknown_version_is_not_found() -> None:
    use_case = GetPublishedCategorySpec(FakeUnitOfWorkFactory())

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=new_tenant_id(), category_id=new_category_id(), version=1)
