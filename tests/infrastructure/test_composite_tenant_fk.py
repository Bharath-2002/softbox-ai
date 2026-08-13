"""The composite tenant-to-tenant foreign key deferred from chunk 3 (D2).

``sessions (tenant_id, user_id)`` -> ``tenant_memberships (tenant_id,
user_id)`` — a session cannot claim an active tenant the user does not
actually belong to. This is a referential-integrity guarantee the database
enforces regardless of RLS, proven directly with SQL rather than through
either repository, because it is a property of the schema, not of any one
port's contract.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.entities.category import Category
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_tenant_id, new_user_id

UowFactory = Callable[[TenantId | None], SqlUnitOfWork]

pytestmark = pytest.mark.db

INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, created_at, updated_at) "
    "VALUES (:id, 't', :slug, 'active', now(), now())"
)
INSERT_USER = text(
    "INSERT INTO users (id, email, email_verified, status, created_at, updated_at) "
    "VALUES (:id, :email, true, 'active', now(), now())"
)
INSERT_MEMBERSHIP = text(
    "INSERT INTO tenant_memberships (id, tenant_id, user_id, role, extra_capabilities, created_at) "
    "VALUES (:id, :tenant_id, :user_id, 'owner', '[]', now())"
)
INSERT_SESSION = text(
    "INSERT INTO sessions "
    "(id, user_id, tenant_id, refresh_token_hash, expires_at, created_at) "
    "VALUES (:id, :user_id, :tenant_id, :hash, now() + interval '30 days', now())"
)


async def test_session_cannot_claim_a_tenant_the_user_does_not_belong_to(
    owner_uow: UowFactory,
) -> None:
    tenant_the_user_belongs_to = new_tenant_id()
    tenant_the_user_does_not_belong_to = new_tenant_id()
    user_id = new_user_id()

    async with owner_uow(None) as uow:
        await uow.session.execute(
            INSERT_TENANT, {"id": str(tenant_the_user_belongs_to), "slug": str(uuid.uuid4())}
        )
        await uow.session.execute(
            INSERT_TENANT,
            {"id": str(tenant_the_user_does_not_belong_to), "slug": str(uuid.uuid4())},
        )
        await uow.session.execute(
            INSERT_USER, {"id": str(user_id), "email": f"{user_id}@example.com"}
        )
        await uow.session.execute(
            INSERT_MEMBERSHIP,
            {
                "id": str(uuid.uuid4()),
                "tenant_id": str(tenant_the_user_belongs_to),
                "user_id": str(user_id),
            },
        )

    # A session for the tenant the user IS a member of: succeeds.
    async with owner_uow(None) as uow:
        await uow.session.execute(
            INSERT_SESSION,
            {
                "id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "tenant_id": str(tenant_the_user_belongs_to),
                "hash": f"valid-{uuid.uuid4()}",
            },
        )

    # A session claiming the tenant the user is NOT a member of: rejected by
    # the composite FK, not merely inconsistent application state.
    with pytest.raises(DBAPIError, match="violates foreign key constraint"):
        async with owner_uow(None) as uow:
            await uow.session.execute(
                INSERT_SESSION,
                {
                    "id": str(uuid.uuid4()),
                    "user_id": str(user_id),
                    "tenant_id": str(tenant_the_user_does_not_belong_to),
                    "hash": f"invalid-{uuid.uuid4()}",
                },
            )


INSERT_CATEGORY = text(
    "INSERT INTO categories "
    "(id, tenant_id, parent_id, path, depth, key, name, slug, position, is_active, "
    "created_at, updated_at) "
    "VALUES (:id, :tenant_id, :parent_id, :path, :depth, :key, :name, :slug, 0, true, "
    "now(), now())"
)


async def test_a_category_cannot_claim_a_parent_from_another_tenant(owner_uow: UowFactory) -> None:
    """``categories (tenant_id, parent_id)`` -> ``categories (tenant_id, id)``
    (D10, D2) - the first composite foreign key in this schema between two
    RLS-forced tables, not merely into a global one. A child row must belong
    to the same tenant as the parent it claims.

    Unlike ``sessions``/``tenant_memberships`` above, ``categories`` is
    itself RLS-forced (FORCE applies to the owner role too) - each insert
    below binds the tenant its own row is tagged as, purely to satisfy
    ``WITH CHECK`` and let the composite FK be the thing that actually gets
    exercised, rather than being masked by an RLS rejection first."""
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()
    parent_in_a = uuid.uuid4()

    async with owner_uow(None) as uow:
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_a), "slug": str(uuid.uuid4())})
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_b), "slug": str(uuid.uuid4())})

    async with owner_uow(tenant_a) as uow:
        await uow.session.execute(
            INSERT_CATEGORY,
            {
                "id": str(parent_in_a),
                "tenant_id": str(tenant_a),
                "parent_id": None,
                "path": str(parent_in_a),
                "depth": 0,
                "key": "root",
                "name": "Root",
                "slug": f"root-{uuid.uuid4()}",
            },
        )

    # A child within tenant A, pointing at tenant A's own root: succeeds.
    child_in_a = uuid.uuid4()
    async with owner_uow(tenant_a) as uow:
        await uow.session.execute(
            INSERT_CATEGORY,
            {
                "id": str(child_in_a),
                "tenant_id": str(tenant_a),
                "parent_id": str(parent_in_a),
                "path": f"{parent_in_a}.{child_in_a}",
                "depth": 1,
                "key": "child",
                "name": "Child",
                "slug": f"child-{uuid.uuid4()}",
            },
        )

    # A row tagged as tenant B, claiming tenant A's root as its parent:
    # rejected by the composite FK, not merely inconsistent application state.
    with pytest.raises(DBAPIError, match="violates foreign key constraint"):
        async with owner_uow(tenant_b) as uow:
            await uow.session.execute(
                INSERT_CATEGORY,
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant_b),
                    "parent_id": str(parent_in_a),
                    "path": f"{parent_in_a}.{uuid.uuid4()}",
                    "depth": 1,
                    "key": "child",
                    "name": "Child",
                    "slug": f"child-{uuid.uuid4()}",
                },
            )


INSERT_ATTRIBUTE_DEFINITION = text(
    "INSERT INTO attribute_definitions "
    "(id, tenant_id, category_id, key, label, data_type, is_required, is_filterable, "
    "is_public, position, validation, ui, created_at, updated_at) "
    "VALUES (:id, :tenant_id, :category_id, :key, :label, 'text', false, false, true, 0, "
    "'{}', '{}', now(), now())"
)


async def test_an_attribute_definition_cannot_claim_a_category_from_another_tenant(
    owner_uow: UowFactory,
) -> None:
    """``attribute_definitions (tenant_id, category_id)`` -> ``categories
    (tenant_id, id)`` (D11, D2) - the second composite FK between two
    RLS-forced tables, and the first that isn't self-referential. A
    definition must belong to the same tenant as the category it claims to
    define a field on."""
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()

    async with owner_uow(None) as uow:
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_a), "slug": str(uuid.uuid4())})
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_b), "slug": str(uuid.uuid4())})

    category_in_a = Category.create(
        tenant_a, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    async with owner_uow(tenant_a) as uow:
        await uow.categories.add(category_in_a)

    # A definition within tenant A, on tenant A's own category: succeeds.
    async with owner_uow(tenant_a) as uow:
        await uow.session.execute(
            INSERT_ATTRIBUTE_DEFINITION,
            {
                "id": str(uuid.uuid4()),
                "tenant_id": str(tenant_a),
                "category_id": str(category_in_a.id),
                "key": "fabric",
                "label": "Fabric",
            },
        )

    # A row tagged as tenant B, claiming tenant A's category: rejected by
    # the composite FK, not merely inconsistent application state.
    with pytest.raises(DBAPIError, match="violates foreign key constraint"):
        async with owner_uow(tenant_b) as uow:
            await uow.session.execute(
                INSERT_ATTRIBUTE_DEFINITION,
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant_b),
                    "category_id": str(category_in_a.id),
                    "key": "fabric",
                    "label": "Fabric",
                },
            )


INSERT_VARIANT_AXIS = text(
    "INSERT INTO variant_axes "
    "(id, tenant_id, category_id, key, label, position, affects_imagery, created_at, updated_at) "
    "VALUES (:id, :tenant_id, :category_id, :key, :key, 0, true, now(), now())"
)
INSERT_VARIANT_AXIS_VALUE = text(
    "INSERT INTO variant_axis_values "
    "(id, tenant_id, axis_id, value, label, created_at, updated_at) "
    "VALUES (:id, :tenant_id, :axis_id, :value, :value, now(), now())"
)


async def test_a_variant_axis_cannot_claim_a_category_from_another_tenant(
    owner_uow: UowFactory,
) -> None:
    """``variant_axes (tenant_id, category_id)`` -> ``categories (tenant_id,
    id)`` (D12, D2) - the same composite-FK shape as
    ``attribute_definitions``."""
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()

    async with owner_uow(None) as uow:
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_a), "slug": str(uuid.uuid4())})
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_b), "slug": str(uuid.uuid4())})

    category_in_a = Category.create(
        tenant_a, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    async with owner_uow(tenant_a) as uow:
        await uow.categories.add(category_in_a)

    with pytest.raises(DBAPIError, match="violates foreign key constraint"):
        async with owner_uow(tenant_b) as uow:
            await uow.session.execute(
                INSERT_VARIANT_AXIS,
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant_b),
                    "category_id": str(category_in_a.id),
                    "key": "colour",
                },
            )


async def test_a_variant_axis_value_cannot_claim_an_axis_from_another_tenant(
    owner_uow: UowFactory,
) -> None:
    """``variant_axis_values (tenant_id, axis_id)`` -> ``variant_axes
    (tenant_id, id)`` (D12, D2) - the first composite FK between two
    RLS-forced tables that is neither self-referential nor pointing at
    ``categories``."""
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()

    async with owner_uow(None) as uow:
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_a), "slug": str(uuid.uuid4())})
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_b), "slug": str(uuid.uuid4())})

    category_in_a = Category.create(
        tenant_a, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    axis_in_a = uuid.uuid4()
    async with owner_uow(tenant_a) as uow:
        await uow.categories.add(category_in_a)
        await uow.session.execute(
            INSERT_VARIANT_AXIS,
            {
                "id": str(axis_in_a),
                "tenant_id": str(tenant_a),
                "category_id": str(category_in_a.id),
                "key": "colour",
            },
        )

    with pytest.raises(DBAPIError, match="violates foreign key constraint"):
        async with owner_uow(tenant_b) as uow:
            await uow.session.execute(
                INSERT_VARIANT_AXIS_VALUE,
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant_b),
                    "axis_id": str(axis_in_a),
                    "value": "maroon",
                },
            )


INSERT_INPUT_IMAGE_SLOT = text(
    "INSERT INTO input_image_slots "
    "(id, tenant_id, category_id, key, label, is_required, position, created_at, updated_at) "
    "VALUES (:id, :tenant_id, :category_id, :key, :key, true, 0, now(), now())"
)
INSERT_CATALOG_IMAGE_SLOT = text(
    "INSERT INTO catalog_image_slots "
    "(id, tenant_id, category_id, key, label, position, aspect_ratio, target_width, "
    "target_height, is_required, created_at, updated_at) "
    "VALUES (:id, :tenant_id, :category_id, :key, :key, 0, '4:5', 1080, 1350, true, now(), now())"
)


async def test_an_input_image_slot_cannot_claim_a_category_from_another_tenant(
    owner_uow: UowFactory,
) -> None:
    """``input_image_slots (tenant_id, category_id)`` -> ``categories
    (tenant_id, id)`` (D13, D2) - same composite-FK shape as
    ``attribute_definitions`` and ``variant_axes``."""
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()

    async with owner_uow(None) as uow:
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_a), "slug": str(uuid.uuid4())})
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_b), "slug": str(uuid.uuid4())})

    category_in_a = Category.create(
        tenant_a, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    async with owner_uow(tenant_a) as uow:
        await uow.categories.add(category_in_a)

    with pytest.raises(DBAPIError, match="violates foreign key constraint"):
        async with owner_uow(tenant_b) as uow:
            await uow.session.execute(
                INSERT_INPUT_IMAGE_SLOT,
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant_b),
                    "category_id": str(category_in_a.id),
                    "key": "border_detail",
                },
            )


async def test_a_catalog_image_slot_cannot_claim_a_category_from_another_tenant(
    owner_uow: UowFactory,
) -> None:
    """``catalog_image_slots (tenant_id, category_id)`` -> ``categories
    (tenant_id, id)`` (D13, D2) - same composite-FK shape as
    ``attribute_definitions`` and ``variant_axes``."""
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()

    async with owner_uow(None) as uow:
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_a), "slug": str(uuid.uuid4())})
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_b), "slug": str(uuid.uuid4())})

    category_in_a = Category.create(
        tenant_a, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    async with owner_uow(tenant_a) as uow:
        await uow.categories.add(category_in_a)

    with pytest.raises(DBAPIError, match="violates foreign key constraint"):
        async with owner_uow(tenant_b) as uow:
            await uow.session.execute(
                INSERT_CATALOG_IMAGE_SLOT,
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": str(tenant_b),
                    "category_id": str(category_in_a.id),
                    "key": "closeup",
                },
            )


INSERT_CATALOG_SLOT_INPUT_REQUIREMENT = text(
    "INSERT INTO catalog_slot_input_requirements "
    "(catalog_image_slot_id, input_image_slot_id, tenant_id, role, prompt_position, "
    "is_required, created_at) "
    "VALUES (:catalog_image_slot_id, :input_image_slot_id, :tenant_id, 'garment_body', 0, "
    "true, now())"
)


async def test_a_requirement_cannot_claim_a_catalog_slot_from_another_tenant(
    owner_uow: UowFactory,
) -> None:
    """``catalog_slot_input_requirements (tenant_id, catalog_image_slot_id)``
    -> ``catalog_image_slots (tenant_id, id)`` (D13, D2) - the first of this
    join's two composite FKs."""
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()

    async with owner_uow(None) as uow:
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_a), "slug": str(uuid.uuid4())})
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_b), "slug": str(uuid.uuid4())})

    category_in_a = Category.create(
        tenant_a, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    catalog_slot_in_a = uuid.uuid4()
    input_slot_in_b = uuid.uuid4()
    category_in_b = Category.create(
        tenant_b, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    async with owner_uow(tenant_a) as uow:
        await uow.categories.add(category_in_a)
        await uow.session.execute(
            INSERT_CATALOG_IMAGE_SLOT,
            {
                "id": str(catalog_slot_in_a),
                "tenant_id": str(tenant_a),
                "category_id": str(category_in_a.id),
                "key": "closeup",
            },
        )
    async with owner_uow(tenant_b) as uow:
        await uow.categories.add(category_in_b)
        await uow.session.execute(
            INSERT_INPUT_IMAGE_SLOT,
            {
                "id": str(input_slot_in_b),
                "tenant_id": str(tenant_b),
                "category_id": str(category_in_b.id),
                "key": "border_detail",
            },
        )

    # tenant_id=b, but the catalog slot belongs to tenant a: rejected by the
    # first composite FK.
    with pytest.raises(DBAPIError, match="violates foreign key constraint"):
        async with owner_uow(tenant_b) as uow:
            await uow.session.execute(
                INSERT_CATALOG_SLOT_INPUT_REQUIREMENT,
                {
                    "catalog_image_slot_id": str(catalog_slot_in_a),
                    "input_image_slot_id": str(input_slot_in_b),
                    "tenant_id": str(tenant_b),
                },
            )


async def test_a_requirement_cannot_claim_an_input_slot_from_another_tenant(
    owner_uow: UowFactory,
) -> None:
    """``catalog_slot_input_requirements (tenant_id, input_image_slot_id)``
    -> ``input_image_slots (tenant_id, id)`` (D13, D2) - the second of this
    join's two composite FKs. Tenant b's own catalog slot is valid, so this
    isolates the failure to the input-slot side rather than either FK."""
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()

    async with owner_uow(None) as uow:
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_a), "slug": str(uuid.uuid4())})
        await uow.session.execute(INSERT_TENANT, {"id": str(tenant_b), "slug": str(uuid.uuid4())})

    category_in_a = Category.create(
        tenant_a, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    category_in_b = Category.create(
        tenant_b, key="apparel", name="Apparel", slug="apparel", parent=None, now=utcnow()
    )
    input_slot_in_a = uuid.uuid4()
    catalog_slot_in_b = uuid.uuid4()
    async with owner_uow(tenant_a) as uow:
        await uow.categories.add(category_in_a)
        await uow.session.execute(
            INSERT_INPUT_IMAGE_SLOT,
            {
                "id": str(input_slot_in_a),
                "tenant_id": str(tenant_a),
                "category_id": str(category_in_a.id),
                "key": "border_detail",
            },
        )
    async with owner_uow(tenant_b) as uow:
        await uow.categories.add(category_in_b)
        await uow.session.execute(
            INSERT_CATALOG_IMAGE_SLOT,
            {
                "id": str(catalog_slot_in_b),
                "tenant_id": str(tenant_b),
                "category_id": str(category_in_b.id),
                "key": "closeup",
            },
        )

    # tenant_id=b and the catalog slot IS b's own - only the input slot is
    # foreign, isolating the rejection to the second FK.
    with pytest.raises(DBAPIError, match="violates foreign key constraint"):
        async with owner_uow(tenant_b) as uow:
            await uow.session.execute(
                INSERT_CATALOG_SLOT_INPUT_REQUIREMENT,
                {
                    "catalog_image_slot_id": str(catalog_slot_in_b),
                    "input_image_slot_id": str(input_slot_in_a),
                    "tenant_id": str(tenant_b),
                },
            )


async def test_session_with_no_tenant_bypasses_the_membership_check(owner_uow: UowFactory) -> None:
    """A platform-plane session with no active tenant has nothing to satisfy
    - a composite FK is not checked when any column in it is NULL."""
    user_id = new_user_id()

    async with owner_uow(None) as uow:
        await uow.session.execute(
            INSERT_USER, {"id": str(user_id), "email": f"{user_id}@example.com"}
        )
        # No tenant_memberships row exists for this user at all.
        await uow.session.execute(
            INSERT_SESSION,
            {
                "id": str(uuid.uuid4()),
                "user_id": str(user_id),
                "tenant_id": None,
                "hash": f"platform-plane-{uuid.uuid4()}",
            },
        )
