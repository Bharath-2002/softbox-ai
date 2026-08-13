"""PublishCategorySpec — builds and stores an immutable snapshot (D15),
stamps ``introduced_in_version`` on newly-owned rows only, advances the
category's version counters, and audits the change.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition
from app.entities.category import Category
from app.features.taxonomy.publish_category_spec import PublishCategorySpec
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


def _use_case() -> tuple[PublishCategorySpec, FakeClock, FakeUnitOfWorkFactory]:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    return PublishCategorySpec(uow_factory, clock), clock, uow_factory


async def test_publishing_an_unknown_category_is_not_found() -> None:
    use_case, _clock, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(), category_id=new_category_id(), actor_user_id=new_user_id()
        )


async def test_first_publish_mints_version_one_and_stamps_owned_rows() -> None:
    use_case, clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    actor_id = new_user_id()
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    fabric = AttributeDefinition.create(
        tenant_id,
        category.id,
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        now=clock.now(),
    )
    await uow_factory.categories.add(category)
    await uow_factory.attribute_definitions.add(fabric)

    version = await use_case(tenant_id=tenant_id, category_id=category.id, actor_user_id=actor_id)

    assert version.version == 1
    assert version.snapshot["attribute_definitions"][0]["key"] == "fabric"

    published_category = await uow_factory.categories.get(tenant_id, category.id)
    assert published_category is not None
    assert published_category.current_spec_version == 1
    assert published_category.draft_spec_version is None

    stamped_fabric = await uow_factory.attribute_definitions.get(tenant_id, fabric.id)
    assert stamped_fabric is not None
    assert stamped_fabric.introduced_in_version == 1

    entries = await uow_factory.audit_log.list_for_subject(tenant_id, "category", category.id)
    assert entries[0].action == "category_spec.published"
    assert entries[0].before == {"current_spec_version": None}
    assert entries[0].after == {"current_spec_version": 1}


async def test_republishing_only_stamps_newly_added_rows() -> None:
    use_case, clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    actor_id = new_user_id()
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    fabric = AttributeDefinition.create(
        tenant_id,
        category.id,
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        now=clock.now(),
    )
    await uow_factory.categories.add(category)
    await uow_factory.attribute_definitions.add(fabric)
    await use_case(tenant_id=tenant_id, category_id=category.id, actor_user_id=actor_id)

    care = AttributeDefinition.create(
        tenant_id,
        category.id,
        key="care_instructions",
        label="Care instructions",
        data_type=AttributeDataType.TEXT,
        now=clock.now(),
    )
    await uow_factory.attribute_definitions.add(care)

    second_version = await use_case(
        tenant_id=tenant_id, category_id=category.id, actor_user_id=actor_id
    )

    assert second_version.version == 2
    fabric_after = await uow_factory.attribute_definitions.get(tenant_id, fabric.id)
    care_after = await uow_factory.attribute_definitions.get(tenant_id, care.id)
    assert fabric_after is not None and fabric_after.introduced_in_version == 1
    assert care_after is not None and care_after.introduced_in_version == 2

    published_category = await uow_factory.categories.get(tenant_id, category.id)
    assert published_category is not None
    assert published_category.current_spec_version == 2


async def test_first_publish_change_summary_lists_every_row_as_added() -> None:
    use_case, clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    actor_id = new_user_id()
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    fabric = AttributeDefinition.create(
        tenant_id,
        category.id,
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        now=clock.now(),
    )
    await uow_factory.categories.add(category)
    await uow_factory.attribute_definitions.add(fabric)

    version = await use_case(tenant_id=tenant_id, category_id=category.id, actor_user_id=actor_id)

    assert version.change_summary is not None
    [change] = version.change_summary["changes"]
    assert change["change_type"] == "added_optional"
    assert change["key"] == "fabric"


async def test_renaming_a_key_between_publishes_is_rejected() -> None:
    use_case, clock, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    actor_id = new_user_id()
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    fabric = AttributeDefinition.create(
        tenant_id,
        category.id,
        key="fabric",
        label="Fabric",
        data_type=AttributeDataType.TEXT,
        now=clock.now(),
    )
    await uow_factory.categories.add(category)
    await uow_factory.attribute_definitions.add(fabric)
    await use_case(tenant_id=tenant_id, category_id=category.id, actor_user_id=actor_id)

    # Same row, key changed in place - not a real feature yet (no Admin API),
    # but the entity is a mutable dataclass and the repository exposes
    # `update`, so this is exactly what a future rename attempt looks like.
    fabric.key = "material"
    await uow_factory.attribute_definitions.update(fabric)

    with pytest.raises(ValidationError, match="not permitted"):
        await use_case(tenant_id=tenant_id, category_id=category.id, actor_user_id=actor_id)

    # Rejected before anything was written - still on version 1.
    published_category = await uow_factory.categories.get(tenant_id, category.id)
    assert published_category is not None
    assert published_category.current_spec_version == 1
