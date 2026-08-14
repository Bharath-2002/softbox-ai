from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.catalog_template import CatalogTemplate
from app.entities.category import Category
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.features.templates.complete_template_analysis import CompleteTemplateAnalysis
from app.shared.errors import NotFoundError
from app.shared.ids import new_asset_id, new_catalog_template_id, new_tenant_id, new_user_id
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


def _use_case() -> tuple[CompleteTemplateAnalysis, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return CompleteTemplateAnalysis(uow_factory, FakeClock(_NOW)), uow_factory


async def test_a_resolvable_prompt_lands_the_template_on_analysed() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    category, closeup = await _seed(uow_factory, tenant_id)
    template = CatalogTemplate.create_from_upload(
        tenant_id,
        closeup.id,
        name="Studio flatlay",
        source_asset_id=new_asset_id(),  # placeholder id - not read by this use case
        created_by=new_user_id(),
        now=_NOW,
    )
    template.start_analysing(now=_NOW)
    await uow_factory.catalog_templates.add(template)

    result = await use_case(
        tenant_id=tenant_id,
        template_id=template.id,
        category_id=category.id,
        analysis={"framing": "flat-lay"},
        prompt_template="{{input.garment_body}} on a plain background",
        analysis_model="fake-vision-model",
    )

    assert result.status.value == "analysed"
    assert result.prompt_template == "{{input.garment_body}} on a plain background"


async def test_an_unresolvable_prompt_lands_the_template_on_invalid() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    category, closeup = await _seed(uow_factory, tenant_id)
    template = CatalogTemplate.create_from_upload(
        tenant_id,
        closeup.id,
        name="Studio flatlay",
        source_asset_id=new_asset_id(),
        created_by=new_user_id(),
        now=_NOW,
    )
    template.start_analysing(now=_NOW)
    await uow_factory.catalog_templates.add(template)

    result = await use_case(
        tenant_id=tenant_id,
        template_id=template.id,
        category_id=category.id,
        analysis=None,
        prompt_template="{{input.nonexistent}}",
        analysis_model="fake-vision-model",
    )

    assert result.status.value == "invalid"
    assert result.analysis_error is not None
    assert "nonexistent" in result.analysis_error


async def test_completing_an_unknown_template_is_not_found() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    category, _closeup = await _seed(uow_factory, tenant_id)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            template_id=new_catalog_template_id(),
            category_id=category.id,
            analysis=None,
            prompt_template="x",
            analysis_model=None,
        )
