"""``UNIQUE (tenant_id, category_id, version)`` (D15) — the guard against a
concurrent double-publish, proven directly against Postgres rather than
through ``PublishCategorySpec`` (whose fake-backed tests cannot exercise a
real constraint). Allocating ``version`` via ``current_spec_version + 1`` is
check-then-act; this constraint is what turns two racing publishes into one
success and one loud ``IntegrityError`` instead of two rows silently
claiming the same version.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.entities.category import Category
from app.entities.category_spec_version import CategorySpecVersion
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id, new_user_id

pytestmark = pytest.mark.db

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', now(), now())"
)
_INSERT_USER = text(
    "INSERT INTO users (id, email, email_verified, status, created_at, updated_at) "
    "VALUES (:id, :email, true, 'active', now(), now())"
)


async def test_two_rows_cannot_claim_the_same_category_and_version(
    owner_uow: Callable[[TenantId | None], SqlUnitOfWork],
) -> None:
    tenant_id = new_tenant_id()
    user_id = new_user_id()
    async with owner_uow(None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {"id": str(tenant_id), "name": f"tenant-{tenant_id.hex[:8]}", "slug": str(tenant_id)},
        )
        await uow.session.execute(
            _INSERT_USER, {"id": str(user_id), "email": f"{user_id}@example.com"}
        )
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    async with owner_uow(tenant_id) as uow:
        await uow.categories.add(category)
        await uow.category_spec_versions.add(
            CategorySpecVersion.create(
                tenant_id, category.id, version=1, snapshot={}, published_by=user_id, now=utcnow()
            )
        )

    with pytest.raises(IntegrityError, match="uq_category_spec_versions_tenant_category_version"):
        async with owner_uow(tenant_id) as uow:
            await uow.category_spec_versions.add(
                CategorySpecVersion.create(
                    tenant_id,
                    category.id,
                    version=1,
                    snapshot={},
                    published_by=user_id,
                    now=utcnow(),
                )
            )
