from __future__ import annotations

from app.entities.product import Product, ProductStatus
from app.shared.clock import utcnow
from app.shared.ids import new_category_id, new_category_spec_version_id, new_tenant_id, new_user_id


def test_a_new_product_starts_in_draft_with_no_promoted_columns_set() -> None:
    product = Product.create(
        new_tenant_id(),
        new_category_id(),
        new_category_spec_version_id(),
        attributes={"colour": "maroon"},
        created_by=new_user_id(),
        now=utcnow(),
    )

    assert product.status == ProductStatus.DRAFT
    assert product.title is None
    assert product.sku is None
    assert product.price_amount is None
    assert product.price_currency is None
    assert product.attributes == {"colour": "maroon"}
