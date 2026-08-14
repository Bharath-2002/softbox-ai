from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.catalog_image import CatalogImage
from app.features.generation.approve_catalog_image import ApproveCatalogImage
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import (
    new_asset_id,
    new_catalog_image_id,
    new_catalog_image_slot_id,
    new_generation_item_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[ApproveCatalogImage, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return ApproveCatalogImage(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed_pending_approval(uow_factory: FakeUnitOfWorkFactory) -> tuple[object, CatalogImage]:
    tenant_id = new_tenant_id()
    image = CatalogImage.create(
        tenant_id,
        new_product_variant_id(),
        new_catalog_image_slot_id(),
        new_asset_id(),
        new_generation_item_id(),
        now=_NOW,
    )
    image.mark_qc_passed(qc_result={"subject_present": True}, now=_NOW)
    await uow_factory.catalog_images.add(image)
    return tenant_id, image


async def test_approving_a_pending_approval_image_records_the_approver() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, image = await _seed_pending_approval(uow_factory)
    approver = new_user_id()

    approved = await use_case(tenant_id=tenant_id, image_id=image.id, approved_by=approver)

    assert approved.status.value == "approved"
    assert approved.approved_by == approver
    assert approved.approved_at == _NOW
    stored = await uow_factory.catalog_images.get(tenant_id, image.id)
    assert stored is not None
    assert stored.status.value == "approved"


async def test_approving_writes_an_audit_log_entry() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, image = await _seed_pending_approval(uow_factory)
    approver = new_user_id()

    await use_case(tenant_id=tenant_id, image_id=image.id, approved_by=approver)

    entries = await uow_factory.audit_log.list_for_subject(tenant_id, "catalog_image", image.id)
    assert len(entries) == 1
    assert entries[0].action == "catalog_image.approved"
    assert entries[0].actor_user_id == approver


async def test_an_unknown_image_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(), image_id=new_catalog_image_id(), approved_by=new_user_id()
        )


async def test_an_image_still_pending_qc_cannot_be_approved() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    image = CatalogImage.create(
        tenant_id,
        new_product_variant_id(),
        new_catalog_image_slot_id(),
        new_asset_id(),
        new_generation_item_id(),
        now=_NOW,
    )
    await uow_factory.catalog_images.add(image)

    with pytest.raises(ValidationError):
        await use_case(tenant_id=tenant_id, image_id=image.id, approved_by=new_user_id())
