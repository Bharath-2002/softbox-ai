from __future__ import annotations

import pytest

from app.entities.product import Product, ProductStatus
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import new_category_id, new_category_spec_version_id, new_tenant_id, new_user_id


def _product() -> Product:
    return Product.create(
        new_tenant_id(),
        new_category_id(),
        new_category_spec_version_id(),
        attributes={"colour": "maroon"},
        created_by=new_user_id(),
        now=utcnow(),
    )


def test_a_new_product_starts_in_draft_with_no_promoted_columns_set() -> None:
    product = _product()

    assert product.status == ProductStatus.DRAFT
    assert product.title is None
    assert product.sku is None
    assert product.price_amount is None
    assert product.price_currency is None
    assert product.attributes == {"colour": "maroon"}


def test_a_draft_product_can_become_ready() -> None:
    product = _product()

    product.mark_ready(now=utcnow())

    assert product.status == ProductStatus.READY


def test_a_ready_product_can_regress_to_needs_attention() -> None:
    product = _product()
    product.mark_ready(now=utcnow())

    product.mark_needs_attention(now=utcnow())

    assert product.status == ProductStatus.NEEDS_ATTENTION


def test_a_needs_attention_product_can_become_ready_again() -> None:
    product = _product()
    product.mark_ready(now=utcnow())
    product.mark_needs_attention(now=utcnow())

    product.mark_ready(now=utcnow())

    assert product.status == ProductStatus.READY


def test_a_draft_product_cannot_need_attention() -> None:
    product = _product()

    with pytest.raises(ValidationError, match="Only a ready product"):
        product.mark_needs_attention(now=utcnow())


def test_a_published_product_cannot_be_marked_ready() -> None:
    product = _product()
    product.status = ProductStatus.PUBLISHED

    with pytest.raises(ValidationError, match="Cannot mark ready"):
        product.mark_ready(now=utcnow())
