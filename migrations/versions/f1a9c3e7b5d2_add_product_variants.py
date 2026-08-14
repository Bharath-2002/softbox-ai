"""add product variants

Revision ID: f1a9c3e7b5d2
Revises: d5f7a2c1e9b3
Create Date: 2026-08-14 11:00:00.000000

Product variants (D12): one row per distinct axis-value combination a
tenant sells. `axis_values` is a flat JSONB map (``{"colour":"maroon"}``),
not a normalised join against `variant_axis_values` — the same
"application-validated JSONB, not a foreign key per value" choice D11 makes
for `products.attributes`; validating a variant's `axis_values` against the
category's declared `variant_axes`/`variant_axis_values` is a use-case
concern (not built yet), not a schema-level constraint.

`attributes` is a **sparse override** of the parent product's attributes —
only the keys this variant changes, never a full copy.

`status` reuses `product_status` (the same `CHECK` values as `products`,
D12's shared "Product / variant lifecycle" diagram), not a second enum.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "f1a9c3e7b5d2"
down_revision: str | None = "d5f7a2c1e9b3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_STATUSES = (
    "draft",
    "ready",
    "needs_attention",
    "generating",
    "review",
    "rejected",
    "approved",
    "publishing",
    "published",
)


def upgrade() -> None:
    op.create_table(
        "product_variants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("sku", sa.Text(), nullable=True),
        sa.Column("axis_values", postgresql.JSONB(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_product_variants_product",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_product_variants_created_by",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_product_variants_tenant_id_id"),
        sa.CheckConstraint(
            "status IN ('" + "','".join(_STATUSES) + "')",
            name="ck_product_variants_status",
        ),
    )
    op.create_index("ix_product_variants_tenant_id", "product_variants", ["tenant_id"])
    op.create_index(
        "ix_product_variants_tenant_product", "product_variants", ["tenant_id", "product_id"]
    )

    enable_rls("product_variants")
    create_tenant_isolation_policy("product_variants")
    grant_to_app_role("product_variants")


def downgrade() -> None:
    op.drop_table("product_variants")
