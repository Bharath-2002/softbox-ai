"""Exercises the real ``StartTemplateAnalysis``/``CompleteTemplateAnalysis``/
``FailTemplateAnalysis`` use cases wired together the way
``bootstrap/di.py`` will wire them - only ``ObjectStorage`` and
``VisionAnalysis`` are fakes. Proves the agent owns no transaction of its
own: every state change happens inside one of the three use cases, and the
agent's ``run`` is just the control flow between them.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.agents.template_analysis import TemplateAnalysisAgent
from app.entities.asset import Asset, AssetKind
from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.catalog_template import CatalogTemplate
from app.entities.category import Category
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.features.templates.complete_template_analysis import CompleteTemplateAnalysis
from app.features.templates.fail_template_analysis import FailTemplateAnalysis
from app.features.templates.start_template_analysis import StartTemplateAnalysis
from app.services.ports.vision_analysis import TemplateAnalysis
from app.shared.errors import NotFoundError
from app.shared.ids import new_catalog_template_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.object_storage import InMemoryObjectStorage
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory
from tests.fakes.vision_analysis import FakeVisionAnalysis

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _agent(
    uow_factory: FakeUnitOfWorkFactory, storage: InMemoryObjectStorage, vision: FakeVisionAnalysis
) -> TemplateAnalysisAgent:
    clock = FakeClock(_NOW)
    return TemplateAnalysisAgent(
        StartTemplateAnalysis(uow_factory, clock),
        CompleteTemplateAnalysis(uow_factory, clock),
        FailTemplateAnalysis(uow_factory, clock),
        storage,
        vision,
    )


async def _seed(
    uow_factory: FakeUnitOfWorkFactory, storage: InMemoryObjectStorage, tenant_id: object
) -> CatalogTemplate:
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

    storage_key = storage.new_storage_key(tenant_id, kind="template", extension="jpg")
    await storage.write(storage_key, b"fake-image-bytes")
    asset = Asset.create(
        tenant_id,
        storage_key=storage_key,
        sha256="a" * 64,
        mime="image/jpeg",
        width=1080,
        height=1350,
        bytes_=17,
        kind=AssetKind.TEMPLATE,
        source="upload",
        now=_NOW,
    )
    await uow_factory.assets.add(asset)

    template = CatalogTemplate.create_from_upload(
        tenant_id,
        closeup.id,
        name="Studio flatlay",
        source_asset_id=asset.id,
        created_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.catalog_templates.add(template)
    return template


async def test_a_successful_analysis_reaches_analysed() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    vision = FakeVisionAnalysis()
    tenant_id = new_tenant_id()
    template = await _seed(uow_factory, storage, tenant_id)
    agent = _agent(uow_factory, storage, vision)

    result = await agent.run(tenant_id=tenant_id, template_id=template.id)

    assert result.status.value == "analysed"
    assert vision.calls == [(b"fake-image-bytes", "image/jpeg")]


async def test_an_unresolvable_prompt_from_the_provider_reaches_invalid() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    vision = FakeVisionAnalysis()
    vision.next_result = TemplateAnalysis(
        analysis={}, prompt_template="{{input.nonexistent}}", model="fake-vision-model"
    )
    tenant_id = new_tenant_id()
    template = await _seed(uow_factory, storage, tenant_id)
    agent = _agent(uow_factory, storage, vision)

    result = await agent.run(tenant_id=tenant_id, template_id=template.id)

    assert result.status.value == "invalid"


async def test_a_provider_failure_reaches_analysis_failed_not_an_unhandled_exception() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    vision = FakeVisionAnalysis()
    vision.next_error = RuntimeError("provider is down")
    tenant_id = new_tenant_id()
    template = await _seed(uow_factory, storage, tenant_id)
    agent = _agent(uow_factory, storage, vision)

    result = await agent.run(tenant_id=tenant_id, template_id=template.id)

    assert result.status.value == "analysis_failed"
    assert result.analysis_error == "provider is down"


async def test_missing_source_bytes_also_reaches_analysis_failed() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    vision = FakeVisionAnalysis()
    tenant_id = new_tenant_id()
    template = await _seed(uow_factory, storage, tenant_id)
    # Delete the bytes after seeding so `ObjectStorage.read` raises NotFoundError
    # inside the agent's try block - a storage failure is just as retryable
    # as a provider failure and must not propagate as an unhandled exception.
    asset = await uow_factory.assets.get(tenant_id, template.source_asset_id)
    assert asset is not None
    await storage.delete(asset.storage_key)
    agent = _agent(uow_factory, storage, vision)

    result = await agent.run(tenant_id=tenant_id, template_id=template.id)

    assert result.status.value == "analysis_failed"


async def test_starting_analysis_still_raises_for_an_unknown_template() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    vision = FakeVisionAnalysis()
    agent = _agent(uow_factory, storage, vision)

    with pytest.raises(NotFoundError):
        await agent.run(tenant_id=new_tenant_id(), template_id=new_catalog_template_id())
