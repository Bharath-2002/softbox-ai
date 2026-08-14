"""add products

Revision ID: d5f7a2c1e9b3
Revises: c4e6b1d9a72f
Create Date: 2026-08-14 10:00:00.000000

Products (D11, D12): one row per product, `attributes` JSONB holding every
tenant-defined field with a GIN index for filtering, plus a handful of
platform-meaningful fields (`title`, `sku`, `price_amount`, `price_currency`)
promoted into real columns by the write path when a category's
`attribute_definitions` tag a field with the matching `semantic_role`. All
four are nullable — a category need not declare any of these roles.

`spec_version_id` is a composite FK to `category_spec_versions`, pinned at
creation (D15) and never updated by this migration's shape (no code path
mutates it — see `entities.product`'s module docstring). `price_amount` is
`BigInteger`, matching `assets.bytes`'s post-widen precedent and CLAUDE.md
§12's "money as integer minor units, never floats."
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "d5f7a2c1e9b3"
down_revision: str | None = "c4e6b1d9a72f"
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
        "products",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("spec_version_id", sa.Uuid(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("sku", sa.Text(), nullable=True),
        sa.Column("price_amount", sa.BigInteger(), nullable=True),
        sa.Column("price_currency", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_products_category",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "spec_version_id"],
            ["category_spec_versions.tenant_id", "category_spec_versions.id"],
            name="fk_products_spec_version",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_products_created_by",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id_id"),
        sa.CheckConstraint(
            "status IN ('" + "','".join(_STATUSES) + "')",
            name="ck_products_status",
        ),
    )
    op.create_index("ix_products_tenant_id", "products", ["tenant_id"])
    op.create_index("ix_products_tenant_category", "products", ["tenant_id", "category_id"])
    op.create_index(
        "ix_products_attributes_gin", "products", ["attributes"], postgresql_using="gin"
    )

    enable_rls("products")
    create_tenant_isolation_policy("products")
    grant_to_app_role("products")


def downgrade() -> None:
    op.drop_table("products")
