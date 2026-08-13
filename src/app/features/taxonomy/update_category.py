"""Edits a category's mutable, non-referential fields — ``name``,
``description``, ``position``, ``is_active``. ``key`` and ``slug`` are
deliberately not editable here: the same "labels are editable in place,
keys carry referential meaning" split D15 already draws for attribute
definitions applies to a category's own ``key`` (it participates in the
materialised ``path`` every descendant's inheritance walk depends on).
Reparenting is ``MoveCategory``'s job, not this use case's.

Takes the full new value of every field rather than optional
partial-update fields — a true PATCH would need a sentinel to distinguish
"leave unchanged" from "set to null" for ``description``, which nothing
calls this with today; simplest thing that works, revisit if a partial
update becomes a real requirement.
"""

from __future__ import annotations

from app.entities.category import Category
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CategoryId, TenantId, UserId


class UpdateCategory:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        category_id: CategoryId,
        name: str,
        description: str | None,
        position: int,
        is_active: bool,
        actor_user_id: UserId,
    ) -> Category:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            category = await uow.categories.get(tenant_id, category_id)
            if category is None:
                raise NotFoundError("Category not found.")

            before = {
                "name": category.name,
                "description": category.description,
                "position": category.position,
                "is_active": category.is_active,
            }

            category.name = name
            category.description = description
            category.position = position
            category.is_active = is_active
            category.updated_at = now
            await uow.categories.update(category)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="category.updated",
                subject_type="category",
                subject_id=category_id,
                before=before,
                after={
                    "name": name,
                    "description": description,
                    "position": position,
                    "is_active": is_active,
                },
                now=now,
            )

            return category
