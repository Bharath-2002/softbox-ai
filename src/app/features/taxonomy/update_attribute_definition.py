"""Edits an attribute definition's non-referential fields. ``key`` and
``data_type`` are not editable — a key change is D15's rename-forbidden
case, and a data-type change after values may already be stored under the
old type is unsafe until M4 has a migration path for existing values.
"""

from __future__ import annotations

from typing import Any

from app.entities.attribute_definition import AttributeDefinition, SemanticRole
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import AttributeDefinitionId, TenantId, UserId


class UpdateAttributeDefinition:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        definition_id: AttributeDefinitionId,
        label: str,
        help_text: str | None,
        semantic_role: SemanticRole | None,
        is_required: bool,
        is_filterable: bool,
        is_public: bool,
        position: int,
        validation: dict[str, Any],
        ui: dict[str, Any],
        default_value: Any | None,
        actor_user_id: UserId,
    ) -> AttributeDefinition:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            definition = await uow.attribute_definitions.get(tenant_id, definition_id)
            if definition is None:
                raise NotFoundError("Attribute definition not found.")

            before = {"label": definition.label, "is_required": definition.is_required}

            definition.label = label
            definition.help_text = help_text
            definition.semantic_role = semantic_role
            definition.is_required = is_required
            definition.is_filterable = is_filterable
            definition.is_public = is_public
            definition.position = position
            definition.validation = validation
            definition.ui = ui
            definition.default_value = default_value
            definition.updated_at = now
            await uow.attribute_definitions.update(definition)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="attribute_definition.updated",
                subject_type="attribute_definition",
                subject_id=definition_id,
                before=before,
                after={"label": label, "is_required": is_required},
                now=now,
            )

            return definition
