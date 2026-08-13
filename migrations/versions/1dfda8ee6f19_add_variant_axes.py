"""add variant axes

Revision ID: 1dfda8ee6f19
Revises: 18c4ff8a7a48
Create Date: 2026-08-14 05:10:00.000000

Generic variant dimensions (D12) — never hardcode "colour". ``affects_imagery``
is what the generation pipeline (M5) fans out over; ``product_variants``
itself is M4 scope, out of this migration.

``variant_axes (tenant_id, category_id)`` -> ``categories (tenant_id, id)``
is the same composite-FK shape ``attribute_definitions`` proved in the
previous migration. ``variant_axis_values (tenant_id, axis_id)`` ->
``variant_axes (tenant_id, id)`` is a new shape: the first composite FK
between two RLS-forced tables that are neither self-referential nor pointing
at ``categories`` — a definition table referencing a *sibling* definition
table it owns.

Unlike ``attribute_definitions.key``, ``variant_axis_values`` gets a real
``UNIQUE (tenant_id, axis_id, value)``: values are an enumerated option set
for one axis with no inheritance/override semantics (D10 only applies to the
axis itself), so two identical values under one axis is unambiguously a bug,
not a legitimate override.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "1dfda8ee6f19"
down_revision: str | None = "18c4ff8a7a48"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "variant_axes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("affects_imagery", sa.Boolean(), nullable=False),
        sa.Column("introduced_in_version", sa.Integer(), nullable=True),
        sa.Column("retired_in_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_variant_axes_category",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_variant_axes_tenant_id_id"),
    )
    op.create_index("ix_variant_axes_tenant_id", "variant_axes", ["tenant_id"])
    op.create_index("ix_variant_axes_tenant_category", "variant_axes", ["tenant_id", "category_id"])

    enable_rls("variant_axes")
    create_tenant_isolation_policy("variant_axes")
    grant_to_app_role("variant_axes")

    op.create_table(
        "variant_axis_values",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("axis_id", sa.Uuid(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "axis_id"],
            ["variant_axes.tenant_id", "variant_axes.id"],
            name="fk_variant_axis_values_axis",
        ),
        sa.UniqueConstraint(
            "tenant_id", "axis_id", "value", name="uq_variant_axis_values_tenant_axis_value"
        ),
    )
    op.create_index("ix_variant_axis_values_tenant_id", "variant_axis_values", ["tenant_id"])
    op.create_index(
        "ix_variant_axis_values_tenant_axis", "variant_axis_values", ["tenant_id", "axis_id"]
    )

    enable_rls("variant_axis_values")
    create_tenant_isolation_policy("variant_axis_values")
    grant_to_app_role("variant_axis_values")


def downgrade() -> None:
    op.drop_table("variant_axis_values")
    op.drop_table("variant_axes")
