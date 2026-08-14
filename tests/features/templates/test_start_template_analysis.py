from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.asset import Asset, AssetKind
from app.entities.catalog_template import CatalogTemplate
from app.entities.image_slots import CatalogImageSlot
from app.features.templates.start_template_analysis import StartTemplateAnalysis
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import new_catalog_template_id, new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed(uow_factory: FakeUnitOfWorkFactory, tenant_id: object) -> tuple[object, object]:
    category_id = new_category_id()
    slot = CatalogImageSlot.create(
        tenant_id,
        category_id,
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=_NOW,
    )
    await uow_factory.catalog_image_slots.add(slot)
    asset = Asset.create(
        tenant_id,
        storage_key="tenants/x/template/a.jpg",
        sha256="a" * 64,
        mime="image/jpeg",
        width=1080,
        height=1350,
        bytes_=204_800,
        kind=AssetKind.TEMPLATE,
        source="upload",
        now=_NOW,
    )
    await uow_factory.assets.add(asset)
    return slot, asset


def _use_case() -> tuple[StartTemplateAnalysis, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return StartTemplateAnalysis(uow_factory, FakeClock(_NOW)), uow_factory


async def test_starting_analysis_transitions_to_analysing_and_returns_context() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot, asset = await _seed(uow_factory, tenant_id)
    template = CatalogTemplate.create_from_upload(
        tenant_id,
        slot.id,
        name="Studio flatlay",
        source_asset_id=asset.id,
        created_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.catalog_templates.add(template)

    ctx = await use_case(tenant_id=tenant_id, template_id=template.id)

    assert ctx.category_id == slot.category_id
    assert ctx.storage_key == asset.storage_key
    assert ctx.mime == asset.mime
    stored = await uow_factory.catalog_templates.get(tenant_id, template.id)
    assert stored is not None
    assert stored.status.value == "analysing"


async def test_starting_analysis_on_an_unknown_template_is_not_found() -> None:
    use_case, _uow_factory = _use_case()
    tenant_id = new_tenant_id()

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=tenant_id, template_id=new_catalog_template_id())


async def test_an_authored_template_cannot_start_vision_analysis() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot, _asset = await _seed(uow_factory, tenant_id)
    template = CatalogTemplate.create_authored(
        tenant_id,
        slot.id,
        name="Marble tabletop",
        prompt_template="x",
        created_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.catalog_templates.add(template)

    with pytest.raises(ValidationError):
        await use_case(tenant_id=tenant_id, template_id=template.id)
