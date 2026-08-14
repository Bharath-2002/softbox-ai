"""Creates a product against its category's *current published* spec (D11,
D15): compiles a Pydantic model straight from the live ``AttributeDefinition``
rows (resolved root-to-leaf, D10) and validates the caller's raw
``attributes`` against it before anything is persisted.

Compiles directly rather than through ``AttributeModelCache`` — the cache
exists to avoid recompiling for repeated reads of an *already-published*
version, but at creation time "live definitions" and "the version about to
be pinned" are the same rows read once; there is no second caller yet to
share the cache with, and wiring it as an app-wide singleton is a caching
optimisation, not a correctness requirement, so it is left for when a
second caller actually needs it.

``price_currency`` is deliberately left ``None``. D11 promotes it as its own
column, but nothing in this codebase yet says where a currency code comes
from for a given ``PRICE``-role attribute — not a tenant-level setting (no
such setting exists) and not the attribute definition itself (``validation``
is a per-datatype constraint bag, not a currency registry). CLAUDE.md §12
requires an integer amount *plus* a currency code; recording an amount with
a guessed currency would be worse than recording it with none. This is a
documented gap, not an oversight — see CHECKLIST.md.
"""

from __future__ import annotations

from typing import Any

import pydantic

from app.entities.attribute_definition import SemanticRole
from app.entities.product import Product
from app.services.attribute_model_compiler import compile_attribute_model
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.spec_inheritance import resolve_inherited
from app.shared.clock import Clock
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import CategoryId, TenantId, UserId


class CreateProduct:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        category_id: CategoryId,
        attributes: dict[str, Any],
        created_by: UserId,
    ) -> Product:
        async with self._uow_factory(tenant_id) as uow:
            category = await uow.categories.get(tenant_id, category_id)
            if category is None:
                raise NotFoundError("Category not found.")
            if category.current_spec_version is None:
                raise ValidationError("This category has no published spec yet.")

            spec_version = await uow.category_spec_versions.get_by_version(
                tenant_id, category_id, category.current_spec_version
            )
            if spec_version is None:
                raise NotFoundError(
                    "The category's published spec version is missing (data inconsistency)."
                )

            chain = category.ancestor_ids()
            rows = await uow.attribute_definitions.list_for_categories(tenant_id, chain)
            definitions = list(resolve_inherited(chain, rows).values())

            model = compile_attribute_model(f"AttributeModel_{category_id.hex}_draft", definitions)
            try:
                validated = model.model_validate(attributes)
            except pydantic.ValidationError as exc:
                raise ValidationError(f"Invalid attributes: {exc}") from exc
            validated_attributes = validated.model_dump(mode="json")

            title: str | None = None
            sku: str | None = None
            price_amount: int | None = None
            for definition in definitions:
                value = validated_attributes.get(definition.key)
                if definition.semantic_role is SemanticRole.TITLE:
                    title = value
                elif definition.semantic_role is SemanticRole.SKU:
                    sku = value
                elif definition.semantic_role is SemanticRole.PRICE:
                    price_amount = value

            now = self._clock.now()
            product = Product.create(
                tenant_id,
                category_id,
                spec_version.id,
                attributes=validated_attributes,
                created_by=created_by,
                now=now,
                title=title,
                sku=sku,
                price_amount=price_amount,
                price_currency=None,
            )
            await uow.products.add(product)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=created_by,
                action="product.created",
                subject_type="product",
                subject_id=product.id,
                before=None,
                after={"category_id": str(category_id)},
                now=now,
            )

            return product
