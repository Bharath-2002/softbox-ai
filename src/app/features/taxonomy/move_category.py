"""Reparents a category, recomputing the materialised path for its whole
subtree in the same transaction (D10). ``audit_log``'s first real caller
(its port docstring named this exact use case in advance) — a category move
changes what a whole subtree of products inherits, so it is exactly the kind
of mutation that port exists to record.
"""

from __future__ import annotations

from app.services.category_hierarchy import reparent_subtree
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CategoryId, TenantId, UserId


class MoveCategory:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        category_id: CategoryId,
        new_parent_id: CategoryId | None,
        actor_user_id: UserId,
    ) -> None:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            category = await uow.categories.get(tenant_id, category_id)
            if category is None:
                raise NotFoundError("Category not found.")

            new_parent = None
            if new_parent_id is not None:
                new_parent = await uow.categories.get(tenant_id, new_parent_id)
                if new_parent is None:
                    raise NotFoundError("Target parent category not found.")

            old_parent_id = category.parent_id
            subtree = await uow.categories.list_subtree(tenant_id, category_id)
            reparent_subtree(category=category, subtree=subtree, new_parent=new_parent, now=now)
            for row in subtree:
                await uow.categories.update(row)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="category.moved",
                subject_type="category",
                subject_id=category_id,
                before={"parent_id": str(old_parent_id) if old_parent_id else None},
                after={"parent_id": str(new_parent_id) if new_parent_id else None},
                now=now,
            )
