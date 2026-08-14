"""Creates an attribute definition (D11) on a category. No sibling-key
uniqueness check here — a descendant may deliberately redefine a key it
inherits (D10); resolution order, not a DB constraint, decides the winner.
"""

from __future__ import annotations

from typing import Any

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition, SemanticRole
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CategoryId, TenantId, UserId


class CreateAttributeDefinition:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        category_id: CategoryId,
        key: str,
        label: str,
        data_type: AttributeDataType,
        help_text: str | None = None,
        semantic_role: SemanticRole | None = None,
        is_required: bool = False,
        is_filterable: bool = False,
        is_public: bool = True,
        position: int = 0,
        validation: dict[str, Any] | None = None,
        ui: dict[str, Any] | None = None,
        default_value: Any | None = None,
        actor_user_id: UserId,
    ) -> AttributeDefinition:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            category = await uow.categories.get(tenant_id, category_id)
            if category is None:
                raise NotFoundError("Category not found.")

            definition = AttributeDefinition.create(
                tenant_id,
                category_id,
                key=key,
                label=label,
                data_type=data_type,
                now=now,
                help_text=help_text,
                semantic_role=semantic_role,
                is_required=is_required,
                is_filterable=is_filterable,
                is_public=is_public,
                position=position,
                validation=validation,
                ui=ui,
                default_value=default_value,
            )
            await uow.attribute_definitions.add(definition)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="attribute_definition.created",
                subject_type="attribute_definition",
                subject_id=definition.id,
                before=None,
                after={"key": key, "category_id": str(category_id)},
                now=now,
            )

            return definition
