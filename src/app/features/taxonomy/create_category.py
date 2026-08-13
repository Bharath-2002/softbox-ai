"""Creates a category (D10) — a thin wrapper around ``Category.create``
plus the transaction/audit boilerplate every M2 write path already follows
(``MoveCategory``, ``PublishCategorySpec``). Sibling-key and tenant-slug
uniqueness are the migration's partial unique indexes, not a check-then-act
lookup here — a duplicate is a 409 (``api/errors.py`` maps the resulting
``IntegrityError`` to ``ConflictError``), not a pre-flight query that could
race a concurrent create.
"""

from __future__ import annotations

from app.entities.category import Category
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.errors import NotFoundError
from app.shared.ids import CategoryId, TenantId, UserId


class CreateCategory:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self,
        *,
        tenant_id: TenantId,
        key: str,
        name: str,
        slug: str,
        parent_id: CategoryId | None,
        description: str | None = None,
        position: int = 0,
        actor_user_id: UserId,
    ) -> Category:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            parent = None
            if parent_id is not None:
                parent = await uow.categories.get(tenant_id, parent_id)
                if parent is None:
                    raise NotFoundError("Parent category not found.")

            category = Category.create(
                tenant_id,
                key=key,
                name=name,
                slug=slug,
                parent=parent,
                now=now,
                description=description,
                position=position,
            )
            await uow.categories.add(category)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="category.created",
                subject_type="category",
                subject_id=category.id,
                before=None,
                after={
                    "key": key,
                    "name": name,
                    "parent_id": str(parent_id) if parent_id else None,
                },
                now=now,
            )

            return category
