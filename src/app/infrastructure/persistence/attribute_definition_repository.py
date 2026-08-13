"""Implements
``app.services.ports.attribute_definition_repository.AttributeDefinitionRepository``.

Filters use ``attribute_definitions_table.c.*``, not the mapped class's own
attributes — see ``user_repository.py`` for why.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.attribute_definition import AttributeDefinition
from app.infrastructure.persistence.mapping import attribute_definitions_table
from app.shared.ids import AttributeDefinitionId, CategoryId, TenantId


class SqlAttributeDefinitionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self, tenant_id: TenantId, definition_id: AttributeDefinitionId
    ) -> AttributeDefinition | None:
        stmt = select(AttributeDefinition).where(
            attribute_definitions_table.c.tenant_id == tenant_id,
            attribute_definitions_table.c.id == definition_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, definition: AttributeDefinition) -> None:
        self._session.add(definition)
        await self._session.flush()

    async def update(self, definition: AttributeDefinition) -> None:
        # Same convention as user_repository.update: `definition` is already
        # the identity-mapped instance, mutated in place by the caller.
        await self._session.flush()

    async def list_for_category(
        self, tenant_id: TenantId, category_id: CategoryId
    ) -> list[AttributeDefinition]:
        stmt = (
            select(AttributeDefinition)
            .where(
                attribute_definitions_table.c.tenant_id == tenant_id,
                attribute_definitions_table.c.category_id == category_id,
            )
            .order_by(attribute_definitions_table.c.position)
        )
        return list((await self._session.execute(stmt)).scalars().all())

    async def list_for_categories(
        self, tenant_id: TenantId, category_ids: list[CategoryId]
    ) -> list[AttributeDefinition]:
        if not category_ids:
            return []
        stmt = (
            select(AttributeDefinition)
            .where(
                attribute_definitions_table.c.tenant_id == tenant_id,
                attribute_definitions_table.c.category_id.in_(category_ids),
            )
            .order_by(attribute_definitions_table.c.position)
        )
        return list((await self._session.execute(stmt)).scalars().all())
