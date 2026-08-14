from __future__ import annotations

import pytest

from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import (
    new_asset_id,
    new_catalog_image_id,
    new_catalog_image_slot_id,
    new_generation_item_id,
    new_product_variant_id,
    new_tenant_id,
)


def _image() -> CatalogImage:
    return CatalogImage.create(
        new_tenant_id(),
        new_product_variant_id(),
        new_catalog_image_slot_id(),
        new_asset_id(),
        new_generation_item_id(),
        now=utcnow(),
    )


def test_a_new_image_starts_pending_qc() -> None:
    image = _image()

    assert image.status == CatalogImageStatus.PENDING_QC
    assert image.qc_result is None
    assert image.rejection_reason is None


def test_passing_qc_reaches_pending_approval_and_records_the_result() -> None:
    image = _image()

    image.mark_qc_passed(qc_result={"subject_present": True}, now=utcnow())

    assert image.status == CatalogImageStatus.PENDING_APPROVAL
    assert image.qc_result == {"subject_present": True}


def test_failing_qc_reaches_qc_failed_and_records_the_result() -> None:
    image = _image()

    image.mark_qc_failed(qc_result={"colour_delta": False}, now=utcnow())

    assert image.status == CatalogImageStatus.QC_FAILED
    assert image.qc_result == {"colour_delta": False}


def test_a_qc_failed_image_can_escalate_to_human_review() -> None:
    image = _image()
    image.mark_qc_failed(qc_result={"colour_delta": False}, now=utcnow())

    image.mark_human_review(reason="retry ladder exhausted", now=utcnow())

    assert image.status == CatalogImageStatus.HUMAN_REVIEW
    assert image.rejection_reason == "retry ladder exhausted"


def test_pending_qc_cannot_escalate_to_human_review_directly() -> None:
    image = _image()

    with pytest.raises(ValidationError):
        image.mark_human_review(reason="x", now=utcnow())


def test_a_passed_image_cannot_fail_qc_again() -> None:
    image = _image()
    image.mark_qc_passed(qc_result={}, now=utcnow())

    with pytest.raises(ValidationError):
        image.mark_qc_failed(qc_result={}, now=utcnow())


def test_an_already_superseded_image_cannot_be_superseded_again() -> None:
    image = _image()
    image.mark_superseded(by=new_catalog_image_id(), now=utcnow())

    with pytest.raises(ValidationError):
        image.mark_superseded(by=new_catalog_image_id(), now=utcnow())
