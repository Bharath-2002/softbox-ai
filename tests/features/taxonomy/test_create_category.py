from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.category import Category
from app.features.taxonomy.create_category import CreateCategory
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


def _use_case() -> tuple[CreateCategory, FakeClock, FakeUnitOfWorkFactory]:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    return CreateCategory(uow_factory, clock), clock, uow_factory


async def test_creating_a_root_category_sets_depth_zero_and_no_parent() -> None:
    use_case, _clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    actor_id = new_user_id()

    category = await use_case(
        tenant_id=tenant_id,
        key="apparel",
        name="Apparel",
        slug="apparel",
        parent_id=None,
        actor_user_id=actor_id,
    )

    assert category.parent_id is None
    assert category.depth == 0
    stored = await uow_factory.categories.get(tenant_id, category.id)
    assert stored is not None and stored.name == "Apparel"


async def test_creating_a_child_category_computes_path_from_the_parent() -> None:
    use_case, clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    actor_id = new_user_id()
    parent = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    await uow_factory.categories.add(parent)

    child = await use_case(
        tenant_id=tenant_id,
        key="sarees",
        name="Sarees",
        slug="sarees",
        parent_id=parent.id,
        actor_user_id=actor_id,
    )

    assert child.parent_id == parent.id
    assert child.depth == 1
    assert child.path == f"{parent.path}.{child.id}"


async def test_creating_under_an_unknown_parent_is_not_found() -> None:
    use_case, _clock, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            key="sarees",
            name="Sarees",
            slug="sarees",
            parent_id=new_category_id(),
            actor_user_id=new_user_id(),
        )


async def test_creation_is_audited() -> None:
    use_case, _clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    actor_id = new_user_id()

    category = await use_case(
        tenant_id=tenant_id,
        key="apparel",
        name="Apparel",
        slug="apparel",
        parent_id=None,
        actor_user_id=actor_id,
    )

    entries = await uow_factory.audit_log.list_for_subject(tenant_id, "category", category.id)
    assert entries[0].action == "category.created"
    assert entries[0].actor_user_id == actor_id
