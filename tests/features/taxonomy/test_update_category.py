from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.category import Category
from app.features.taxonomy.update_category import UpdateCategory
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


def _use_case() -> tuple[UpdateCategory, FakeClock, FakeUnitOfWorkFactory]:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    return UpdateCategory(uow_factory, clock), clock, uow_factory


async def test_update_replaces_the_editable_fields() -> None:
    use_case, clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    actor_id = new_user_id()
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    await uow_factory.categories.add(category)

    updated = await use_case(
        tenant_id=tenant_id,
        category_id=category.id,
        name="Apparel (renamed)",
        description="A description",
        position=3,
        is_active=False,
        actor_user_id=actor_id,
    )

    assert updated.name == "Apparel (renamed)"
    assert updated.description == "A description"
    assert updated.position == 3
    assert updated.is_active is False
    # key/slug/path/depth untouched.
    assert updated.key == "apparel"
    assert updated.slug == "apparel"


async def test_update_does_not_touch_key_or_slug() -> None:
    use_case, clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    await uow_factory.categories.add(category)

    updated = await use_case(
        tenant_id=tenant_id,
        category_id=category.id,
        name="Apparel",
        description=None,
        position=0,
        is_active=True,
        actor_user_id=new_user_id(),
    )

    assert updated.key == "apparel"
    assert updated.slug == "apparel"


async def test_updating_an_unknown_category_is_not_found() -> None:
    use_case, _clock, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            category_id=new_category_id(),
            name="X",
            description=None,
            position=0,
            is_active=True,
            actor_user_id=new_user_id(),
        )


async def test_update_is_audited_with_before_and_after() -> None:
    use_case, clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    actor_id = new_user_id()
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    await uow_factory.categories.add(category)

    await use_case(
        tenant_id=tenant_id,
        category_id=category.id,
        name="Renamed",
        description=None,
        position=0,
        is_active=True,
        actor_user_id=actor_id,
    )

    entries = await uow_factory.audit_log.list_for_subject(tenant_id, "category", category.id)
    assert entries[0].action == "category.updated"
    assert entries[0].before["name"] == "Apparel"
    assert entries[0].after["name"] == "Renamed"
