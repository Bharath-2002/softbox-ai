"""MoveCategory — reparents a category and recomputes the materialised path
for its whole subtree in one transaction, and audits the move.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.category import Category
from app.features.taxonomy.move_category import MoveCategory
from app.shared.errors import NotFoundError
from app.shared.ids import new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


def _use_case() -> tuple[MoveCategory, FakeClock, FakeUnitOfWorkFactory]:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    return MoveCategory(uow_factory, clock), clock, uow_factory


async def test_moving_a_mid_tree_node_updates_the_whole_subtree_and_audits_it() -> None:
    use_case, clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    actor_id = new_user_id()
    root = Category.create(tenant_id, key="a", name="A", slug="a", parent=None, now=clock.now())
    mid = Category.create(tenant_id, key="b", name="B", slug="b", parent=root, now=clock.now())
    leaf = Category.create(tenant_id, key="c", name="C", slug="c", parent=mid, now=clock.now())
    other_root = Category.create(
        tenant_id, key="d", name="D", slug="d", parent=None, now=clock.now()
    )
    for category in (root, mid, leaf, other_root):
        await uow_factory.categories.add(category)

    await use_case(
        tenant_id=tenant_id,
        category_id=mid.id,
        new_parent_id=other_root.id,
        actor_user_id=actor_id,
    )

    moved_mid = await uow_factory.categories.get(tenant_id, mid.id)
    moved_leaf = await uow_factory.categories.get(tenant_id, leaf.id)
    assert moved_mid is not None and moved_leaf is not None
    assert moved_mid.parent_id == other_root.id
    assert moved_mid.path == f"{other_root.path}.{mid.id}"
    assert moved_leaf.path == f"{moved_mid.path}.{leaf.id}"

    entries = await uow_factory.audit_log.list_for_subject(tenant_id, "category", mid.id)
    assert entries[0].action == "category.moved"
    assert entries[0].actor_user_id == actor_id
    assert entries[0].after == {"parent_id": str(other_root.id)}


async def test_moving_an_unknown_category_is_not_found() -> None:
    use_case, _clock, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            category_id=new_category_id(),
            new_parent_id=None,
            actor_user_id=new_user_id(),
        )


async def test_moving_to_an_unknown_parent_is_not_found() -> None:
    use_case, clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    root = Category.create(tenant_id, key="a", name="A", slug="a", parent=None, now=clock.now())
    await uow_factory.categories.add(root)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            category_id=root.id,
            new_parent_id=new_category_id(),
            actor_user_id=new_user_id(),
        )
