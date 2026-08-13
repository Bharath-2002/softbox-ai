"""Runs against both InMemoryCatalogSlotInputRequirementRepository and
SqlCatalogSlotInputRequirementRepository. The real leg seeds a tenant, a
category, one catalog slot and two input slots, so the requirement's two
composite FKs have something real to point at.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.infrastructure.persistence.catalog_slot_input_requirement_repository import (
    SqlCatalogSlotInputRequirementRepository,
)
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.services.ports.catalog_slot_input_requirement_repository import (
    CatalogSlotInputRequirementRepository,
)
from app.shared.clock import utcnow
from app.shared.ids import (
    CatalogImageSlotId,
    InputImageSlotId,
    TenantId,
    new_catalog_image_slot_id,
    new_category_id,
    new_input_image_slot_id,
    new_tenant_id,
)
from tests.fakes.catalog_slot_input_requirement_repository import (
    InMemoryCatalogSlotInputRequirementRepository,
)
from tests.infrastructure.conftest import APP_URL, OWNER_URL

pytestmark = pytest.mark.db

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")
_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)
_INSERT_CATEGORY = text(
    "INSERT INTO categories "
    "(id, tenant_id, parent_id, path, depth, key, name, slug, position, is_active, "
    "created_at, updated_at) "
    "VALUES (:id, :tenant_id, NULL, :path, 0, :key, :key, :slug, 0, true, now(), now())"
)
_INSERT_CATALOG_SLOT = text(
    "INSERT INTO catalog_image_slots "
    "(id, tenant_id, category_id, key, label, position, aspect_ratio, target_width, "
    "target_height, is_required, created_at, updated_at) "
    "VALUES (:id, :tenant_id, :category_id, :key, :key, 0, '4:5', 1080, 1350, true, now(), now())"
)
_INSERT_INPUT_SLOT = text(
    "INSERT INTO input_image_slots "
    "(id, tenant_id, category_id, key, label, is_required, position, created_at, updated_at) "
    "VALUES (:id, :tenant_id, :category_id, :key, :key, true, 0, now(), now())"
)


@dataclass
class Context:
    requirements: CatalogSlotInputRequirementRepository
    tenant_id: TenantId
    catalog_image_slot_id: CatalogImageSlotId
    input_image_slot_id: InputImageSlotId
    other_input_image_slot_id: InputImageSlotId


async def _make_real_fixture() -> tuple[
    TenantId, CatalogImageSlotId, InputImageSlotId, InputImageSlotId
]:
    tenant_id = new_tenant_id()
    category_id = new_category_id()
    catalog_slot_id = new_catalog_image_slot_id()
    input_slot_id = new_input_image_slot_id()
    other_input_slot_id = new_input_image_slot_id()
    engine = create_engine(OWNER_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(
        _INSERT_TENANT,
        {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
    )
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    await session.execute(
        _INSERT_CATEGORY,
        {
            "id": str(category_id),
            "tenant_id": str(tenant_id),
            "path": str(category_id),
            "key": str(category_id),
            "slug": str(category_id),
        },
    )
    await session.execute(
        _INSERT_CATALOG_SLOT,
        {
            "id": str(catalog_slot_id),
            "tenant_id": str(tenant_id),
            "category_id": str(category_id),
            "key": "closeup",
        },
    )
    for slot_id, key in ((input_slot_id, "border"), (other_input_slot_id, "panel_b")):
        await session.execute(
            _INSERT_INPUT_SLOT,
            {
                "id": str(slot_id),
                "tenant_id": str(tenant_id),
                "category_id": str(category_id),
                "key": key,
            },
        )
    await session.commit()
    await session.close()
    await engine.dispose()
    return tenant_id, catalog_slot_id, input_slot_id, other_input_slot_id


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        yield Context(
            InMemoryCatalogSlotInputRequirementRepository(),
            new_tenant_id(),
            new_catalog_image_slot_id(),
            new_input_image_slot_id(),
            new_input_image_slot_id(),
        )
        return

    tenant_id, catalog_slot_id, input_slot_id, other_input_slot_id = await _make_real_fixture()
    engine = create_engine(APP_URL)
    session = create_session_factory(engine)()
    await session.begin()
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
    try:
        yield Context(
            SqlCatalogSlotInputRequirementRepository(session),
            tenant_id,
            catalog_slot_id,
            input_slot_id,
            other_input_slot_id,
        )
    finally:
        await session.rollback()
        await session.close()
        await engine.dispose()


async def test_unknown_requirement_returns_none(ctx: Context) -> None:
    assert (
        await ctx.requirements.get(
            ctx.tenant_id, ctx.catalog_image_slot_id, ctx.input_image_slot_id
        )
        is None
    )


async def test_add_then_get_round_trips(ctx: Context) -> None:
    requirement = CatalogSlotInputRequirement.create(
        ctx.tenant_id,
        ctx.catalog_image_slot_id,
        ctx.input_image_slot_id,
        role="garment_body",
        prompt_position=0,
        now=utcnow(),
    )

    await ctx.requirements.add(requirement)

    fetched = await ctx.requirements.get(
        ctx.tenant_id, ctx.catalog_image_slot_id, ctx.input_image_slot_id
    )
    assert fetched is not None
    assert fetched.role == "garment_body"


async def test_list_for_catalog_slot_is_ordered_by_prompt_position(ctx: Context) -> None:
    second = CatalogSlotInputRequirement.create(
        ctx.tenant_id,
        ctx.catalog_image_slot_id,
        ctx.other_input_image_slot_id,
        role="border_detail",
        prompt_position=1,
        now=utcnow(),
    )
    first = CatalogSlotInputRequirement.create(
        ctx.tenant_id,
        ctx.catalog_image_slot_id,
        ctx.input_image_slot_id,
        role="garment_body",
        prompt_position=0,
        now=utcnow(),
    )
    await ctx.requirements.add(second)
    await ctx.requirements.add(first)

    listed = await ctx.requirements.list_for_catalog_slot(ctx.tenant_id, ctx.catalog_image_slot_id)

    assert [r.role for r in listed] == ["garment_body", "border_detail"]


async def test_list_for_input_slot_finds_every_catalog_slot_using_it(ctx: Context) -> None:
    """The reverse lookup the admin UI's "attach to a second catalog slot"
    affordance needs (D13)."""
    requirement = CatalogSlotInputRequirement.create(
        ctx.tenant_id,
        ctx.catalog_image_slot_id,
        ctx.input_image_slot_id,
        role="garment_body",
        prompt_position=0,
        now=utcnow(),
    )
    await ctx.requirements.add(requirement)

    listed = await ctx.requirements.list_for_input_slot(ctx.tenant_id, ctx.input_image_slot_id)

    assert len(listed) == 1
    assert listed[0].catalog_image_slot_id == ctx.catalog_image_slot_id


async def test_remove_deletes_the_pairing(ctx: Context) -> None:
    requirement = CatalogSlotInputRequirement.create(
        ctx.tenant_id,
        ctx.catalog_image_slot_id,
        ctx.input_image_slot_id,
        role="garment_body",
        prompt_position=0,
        now=utcnow(),
    )
    await ctx.requirements.add(requirement)

    await ctx.requirements.remove(ctx.tenant_id, ctx.catalog_image_slot_id, ctx.input_image_slot_id)

    assert (
        await ctx.requirements.get(
            ctx.tenant_id, ctx.catalog_image_slot_id, ctx.input_image_slot_id
        )
        is None
    )


async def test_update_persists_mutated_fields(ctx: Context) -> None:
    requirement = CatalogSlotInputRequirement.create(
        ctx.tenant_id,
        ctx.catalog_image_slot_id,
        ctx.input_image_slot_id,
        role="garment_body",
        prompt_position=0,
        now=utcnow(),
    )
    await ctx.requirements.add(requirement)

    requirement.role = "garment_body_revised"
    await ctx.requirements.update(requirement)

    fetched = await ctx.requirements.get(
        ctx.tenant_id, ctx.catalog_image_slot_id, ctx.input_image_slot_id
    )
    assert fetched is not None
    assert fetched.role == "garment_body_revised"
