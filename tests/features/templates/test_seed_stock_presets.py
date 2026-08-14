from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.category import Category
from app.entities.image_slots import CatalogImageSlot
from app.features.templates.seed_stock_presets import (
    DEFAULT_STOCK_SCENE_PRESETS,
    SeedStockPresets,
)
from app.shared.errors import NotFoundError
from app.shared.ids import new_catalog_image_slot_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed_slot(uow_factory: FakeUnitOfWorkFactory, tenant_id: object) -> CatalogImageSlot:
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)
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
    return closeup


def _use_case() -> tuple[SeedStockPresets, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return SeedStockPresets(uow_factory, FakeClock(_NOW)), uow_factory


async def test_every_default_preset_reaches_analysed() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot = await _seed_slot(uow_factory, tenant_id)

    seeded = await use_case(
        tenant_id=tenant_id, catalog_image_slot_id=slot.id, actor_user_id=new_user_id()
    )

    assert len(seeded) == len(DEFAULT_STOCK_SCENE_PRESETS)
    assert all(template.status.value == "analysed" for template in seeded)
    assert all(template.kind.value == "authored_scene" for template in seeded)
    assert [template.name for template in seeded] == [
        name for name, _ in DEFAULT_STOCK_SCENE_PRESETS
    ]


async def test_seeding_twice_bumps_every_preset_to_version_two() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot = await _seed_slot(uow_factory, tenant_id)

    await use_case(tenant_id=tenant_id, catalog_image_slot_id=slot.id, actor_user_id=new_user_id())
    second = await use_case(
        tenant_id=tenant_id, catalog_image_slot_id=slot.id, actor_user_id=new_user_id()
    )

    assert all(template.version == 2 for template in second)


async def test_seeding_against_an_unknown_catalog_slot_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            catalog_image_slot_id=new_catalog_image_slot_id(),
            actor_user_id=new_user_id(),
        )


async def test_a_custom_preset_list_can_be_seeded_instead() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    slot = await _seed_slot(uow_factory, tenant_id)

    seeded = await use_case(
        tenant_id=tenant_id,
        catalog_image_slot_id=slot.id,
        actor_user_id=new_user_id(),
        presets=(("Custom scene", "A plain custom scene, no placeholders."),),
    )

    assert len(seeded) == 1
    assert seeded[0].name == "Custom scene"
