"""add input and catalog image slots

Revision ID: f456e393914a
Revises: 1dfda8ee6f19
Create Date: 2026-08-14 06:00:00.000000

The two pool-definition tables behind D13 - one photograph feeding several
catalog images. ``input_image_slots`` is what gets captured;
``catalog_image_slots`` is what gets produced. Neither references the
other here; the sharing join (``catalog_slot_input_requirements``) is the
next migration, once both sides it references exist.

Both follow the same composite-FK shape ``attribute_definitions`` and
``variant_axes`` already established: ``(tenant_id, category_id)`` ->
``categories (tenant_id, id)``.

``example_asset_id`` is a bare ``uuid`` column, no foreign key - ``assets``
does not exist until M3 (same reasoning as ``audit_log.actor_user_id``
before ``users`` existed, chunk 3's migration).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "f456e393914a"
down_revision: str | None = "1dfda8ee6f19"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "input_image_slots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("capture_guidance", sa.Text(), nullable=True),
        sa.Column("example_asset_id", sa.Uuid(), nullable=True),
        sa.Column("normalisation", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("introduced_in_version", sa.Integer(), nullable=True),
        sa.Column("retired_in_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_input_image_slots_category",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_input_image_slots_tenant_id_id"),
    )
    op.create_index("ix_input_image_slots_tenant_id", "input_image_slots", ["tenant_id"])
    op.create_index(
        "ix_input_image_slots_tenant_category", "input_image_slots", ["tenant_id", "category_id"]
    )

    enable_rls("input_image_slots")
    create_tenant_isolation_policy("input_image_slots")
    grant_to_app_role("input_image_slots")

    op.create_table(
        "catalog_image_slots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("aspect_ratio", sa.Text(), nullable=False),
        sa.Column("target_width", sa.Integer(), nullable=False),
        sa.Column("target_height", sa.Integer(), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("introduced_in_version", sa.Integer(), nullable=True),
        sa.Column("retired_in_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_catalog_image_slots_category",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_image_slots_tenant_id_id"),
    )
    op.create_index("ix_catalog_image_slots_tenant_id", "catalog_image_slots", ["tenant_id"])
    op.create_index(
        "ix_catalog_image_slots_tenant_category",
        "catalog_image_slots",
        ["tenant_id", "category_id"],
    )

    enable_rls("catalog_image_slots")
    create_tenant_isolation_policy("catalog_image_slots")
    grant_to_app_role("catalog_image_slots")


def downgrade() -> None:
    op.drop_table("catalog_image_slots")
    op.drop_table("input_image_slots")
