"""Exercises the real ``StartInputImageValidation``/
``CompleteInputImageValidation`` use cases wired together the way
``bootstrap/di.py`` will wire them — only ``ObjectStorage`` is a fake.
Proves the agent owns no transaction of its own, the same property
``test_template_analysis.py`` proves for ``TemplateAnalysisAgent``.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.agents.input_image_validation import InputImageValidationAgent
from app.entities.asset import Asset, AssetKind
from app.entities.product_input_image import ProductInputImage
from app.features.products.complete_input_image_validation import CompleteInputImageValidation
from app.features.products.start_input_image_validation import StartInputImageValidation
from app.shared.clock import utcnow
from app.shared.errors import NotFoundError
from app.shared.ids import (
    new_input_image_slot_id,
    new_product_id,
    new_product_input_image_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.object_storage import InMemoryObjectStorage
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = utcnow()


def _sharp_jpeg_bytes(size: int = 800) -> bytes:
    image = Image.new("L", (size, size))
    pixels = image.load()
    square = 20
    for y in range(size):
        for x in range(size):
            pixels[x, y] = 255 if (x // square + y // square) % 2 == 0 else 0
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG")
    return buf.getvalue()


def _agent(
    uow_factory: FakeUnitOfWorkFactory, storage: InMemoryObjectStorage
) -> InputImageValidationAgent:
    clock = FakeClock(_NOW)
    return InputImageValidationAgent(
        StartInputImageValidation(uow_factory, clock),
        CompleteInputImageValidation(uow_factory, clock),
        storage,
    )


async def _seed(
    uow_factory: FakeUnitOfWorkFactory,
    storage: InMemoryObjectStorage,
    tenant_id: object,
    data: bytes,
) -> ProductInputImage:
    storage_key = storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    await storage.write(storage_key, data)
    asset = Asset.create(
        tenant_id,
        storage_key=storage_key,
        sha256="a" * 64,
        mime="image/jpeg",
        width=800,
        height=800,
        bytes_=len(data),
        kind=AssetKind.INPUT,
        source="upload",
        now=_NOW,
    )
    await uow_factory.assets.add(asset)
    image = ProductInputImage.create(
        tenant_id,
        new_product_id(),
        input_image_slot_id=new_input_image_slot_id(),
        asset_id=asset.id,
        created_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.product_input_images.add(image)
    return image


async def test_a_sharp_well_exposed_image_reaches_ready() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    tenant_id = new_tenant_id()
    image = await _seed(uow_factory, storage, tenant_id, _sharp_jpeg_bytes())
    agent = _agent(uow_factory, storage)

    result = await agent.run(tenant_id=tenant_id, image_id=image.id)

    assert result.status.value == "ready"


async def test_a_flat_image_reaches_rejected_with_an_actionable_reason() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    tenant_id = new_tenant_id()
    buf = io.BytesIO()
    Image.new("RGB", (800, 800), color=(128, 128, 128)).save(buf, format="JPEG")
    image = await _seed(uow_factory, storage, tenant_id, buf.getvalue())
    agent = _agent(uow_factory, storage)

    result = await agent.run(tenant_id=tenant_id, image_id=image.id)

    assert result.status.value == "rejected"
    assert result.rejection_reason is not None
    assert (
        "retake" in result.rejection_reason.lower() or "blurry" in result.rejection_reason.lower()
    )


async def test_missing_source_bytes_reaches_rejected_not_an_unhandled_exception() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    tenant_id = new_tenant_id()
    image = await _seed(uow_factory, storage, tenant_id, _sharp_jpeg_bytes())
    asset = await uow_factory.assets.get(tenant_id, image.asset_id)
    assert asset is not None
    await storage.delete(asset.storage_key)
    agent = _agent(uow_factory, storage)

    result = await agent.run(tenant_id=tenant_id, image_id=image.id)

    assert result.status.value == "rejected"
    assert result.rejection_reason is not None


async def test_starting_validation_still_raises_for_an_unknown_image() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    storage = InMemoryObjectStorage()
    agent = _agent(uow_factory, storage)

    with pytest.raises(NotFoundError):
        await agent.run(tenant_id=new_tenant_id(), image_id=new_product_input_image_id())
