from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.category import Category
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.features.templates.create_authored_template import CreateAuthoredTemplate
from app.shared.errors import NotFoundError
from app.shared.ids import new_catalog_image_slot_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed(uow_factory: FakeUnitOfWorkFactory, tenant_id: object) -> tuple[object, object]:
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)
    garment_body = InputImageSlot.create(
        tenant_id, category.id, key="garment_body", label="Garment body", now=_NOW
    )
    await uow_factory.input_image_slots.add(garment_body)
    closeup = CatalogImageSlot.create(
        tenant_id,
        category.id,
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=_NOW,
    )
    await uow_factory.catalog_image_slots.add(closeup)
    requirement = CatalogSlotInputRequirement.create(
        tenant_id, closeup.id, garment_body.id, role="garment_body", prompt_position=0, now=_NOW
    )
    await uow_factory.catalog_slot_input_requirements.add(requirement)
    return category, closeup


def _use_case() -> tuple[CreateAuthoredTemplate, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return CreateAuthoredTemplate(uow_factory, FakeClock(_NOW)), uow_factory


async def test_a_resolvable_authored_template_reaches_analysed_immediately() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    _category, closeup = await _seed(uow_factory, tenant_id)

    template = await use_case(
        tenant_id=tenant_id,
        catalog_image_slot_id=closeup.id,
        name="Marble tabletop",
        prompt_template="{{input.garment_body}} on white marble, soft daylight.",
        actor_user_id=new_user_id(),
    )

    assert template.status.value == "analysed"
    assert template.version == 1


async def test_an_unresolvable_authored_template_reaches_invalid() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    _category, closeup = await _seed(uow_factory, tenant_id)

    template = await use_case(
        tenant_id=tenant_id,
        catalog_image_slot_id=closeup.id,
        name="Marble tabletop",
        prompt_template="{{input.nonexistent}}",
        actor_user_id=new_user_id(),
    )

    assert template.status.value == "invalid"
    assert template.analysis_error is not None


async def test_recreating_the_same_name_bumps_the_version() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    _category, closeup = await _seed(uow_factory, tenant_id)

    first = await use_case(
        tenant_id=tenant_id,
        catalog_image_slot_id=closeup.id,
        name="Marble tabletop",
        prompt_template="A plain scene.",
        actor_user_id=new_user_id(),
    )
    second = await use_case(
        tenant_id=tenant_id,
        catalog_image_slot_id=closeup.id,
        name="Marble tabletop",
        prompt_template="A different plain scene.",
        actor_user_id=new_user_id(),
    )

    assert first.version == 1
    assert second.version == 2
    assert second.id != first.id


async def test_creating_against_an_unknown_catalog_slot_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            catalog_image_slot_id=new_catalog_image_slot_id(),
            name="Marble tabletop",
            prompt_template="A plain scene.",
            actor_user_id=new_user_id(),
        )
