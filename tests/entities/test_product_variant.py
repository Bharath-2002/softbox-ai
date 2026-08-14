from __future__ import annotations

from app.entities.product import ProductStatus
from app.entities.product_variant import ProductVariant
from app.shared.clock import utcnow
from app.shared.ids import new_product_id, new_tenant_id, new_user_id


def test_a_new_variant_starts_in_draft_with_empty_attribute_overrides() -> None:
    variant = ProductVariant.create(
        new_tenant_id(),
        new_product_id(),
        axis_values={"colour": "maroon"},
        created_by=new_user_id(),
        now=utcnow(),
    )

    assert variant.status == ProductStatus.DRAFT
    assert variant.axis_values == {"colour": "maroon"}
    assert variant.attributes == {}
    assert variant.sku is None
    assert variant.is_default is False
