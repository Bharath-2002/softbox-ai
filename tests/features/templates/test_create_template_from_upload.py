from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.asset import Asset, AssetKind
from app.entities.image_slots import CatalogImageSlot
from app.features.templates.create_template_from_upload import CreateTemplateFromUpload
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import new_asset_id, new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed_slot(uow_factory: FakeUnitOfWorkFactory, tenant_id: object) -> object:
    slot = CatalogImageSlot.create(
        tenant_id,
        new_category_id(),
        key="closeup",
        label="Close-up",
        aspect_ratio="4:5",
        target_width=1080,
        target_height=1350,
        now=_NOW,
    )
    await uow_factory.catalog_image_slots.add(slot)
    return slot


async def _seed_asset(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: object, kind: AssetKind = AssetKind.TEMPLATE
) -> object:
    asset = Asset.create(
        tenant_id,
        storage_key="tenants/x/template/a.jpg",
        sha256="a" * 64,
        mime="image/jpeg",
        width=1080,
        height=1350,
        bytes_=204_800,
        kind=kind,
        source="upload",
        now=_NOW,
    )
    await uow_factory.assets.add(asset)
    return asset


def _use_case() -> tuple[CreateTemplateFromUpload, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return CreateTemplateFromUpload(uow_factory, FakeClock(_NOW)), uow_factory


async def test_creating_from_an_upload_lands_in_uploaded() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot = await _seed_slot(uow_factory, tenant_id)
    asset = await _seed_asset(uow_factory, tenant_id)

    template = await use_case(
        tenant_id=tenant_id,
        catalog_image_slot_id=slot.id,
        name="Studio flatlay",
        source_asset_id=asset.id,
        actor_user_id=new_user_id(),
    )

    assert template.status.value == "uploaded"
    assert template.source_asset_id == asset.id
    assert template.version == 1


async def test_an_asset_that_is_not_a_template_kind_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot = await _seed_slot(uow_factory, tenant_id)
    asset = await _seed_asset(uow_factory, tenant_id, kind=AssetKind.INPUT)

    with pytest.raises(ValidationError):
        await use_case(
            tenant_id=tenant_id,
            catalog_image_slot_id=slot.id,
            name="Studio flatlay",
            source_asset_id=asset.id,
            actor_user_id=new_user_id(),
        )


async def test_an_unknown_source_asset_is_not_found() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot = await _seed_slot(uow_factory, tenant_id)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            catalog_image_slot_id=slot.id,
            name="Studio flatlay",
            source_asset_id=new_asset_id(),
            actor_user_id=new_user_id(),
        )
