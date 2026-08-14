"""add product input images

Revision ID: a7d3e5c9f1b8
Revises: f1a9c3e7b5d2
Create Date: 2026-08-14 12:00:00.000000

Captured input photos (D12, §6.1). `variant_id` is nullable — NULL means
shared across every variant of the product; a real value means the image
belongs to one specific variant (A6's "photographed" colour-variant path).
The D12 resolution rule itself (variant image wins, else the product's)
lives in `services.input_image_resolution`, a pure function, not a query
here.

`asset_id` is the original upload (always retained, §6.1); `normalised_asset_id`
is nullable, set once the normalising step (not built yet — no adapter
exists, see `entities.product_input_image`'s module docstring) produces a
derivative. Both are composite FKs to `assets`.

`status` runs its own state machine (`captured -> validating -> normalising
-> ready / rejected`), independent of `product_status` — a single input
image's processing state is not the same axis as its product's or variant's
overall lifecycle.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role

revision: str = "a7d3e5c9f1b8"
down_revision: str | None = "f1a9c3e7b5d2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_STATUSES = ("captured", "validating", "normalising", "ready", "rejected")


def upgrade() -> None:
    op.create_table(
        "product_input_images",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=True),
        sa.Column("input_image_slot_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("normalised_asset_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_product_input_images_product",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_product_input_images_variant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "input_image_slot_id"],
            ["input_image_slots.tenant_id", "input_image_slots.id"],
            name="fk_product_input_images_slot",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["assets.tenant_id", "assets.id"],
            name="fk_product_input_images_asset",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "normalised_asset_id"],
            ["assets.tenant_id", "assets.id"],
            name="fk_product_input_images_normalised_asset",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_product_input_images_created_by",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_product_input_images_tenant_id_id"),
        sa.CheckConstraint(
            "status IN ('" + "','".join(_STATUSES) + "')",
            name="ck_product_input_images_status",
        ),
    )
    op.create_index("ix_product_input_images_tenant_id", "product_input_images", ["tenant_id"])
    op.create_index(
        "ix_product_input_images_tenant_product",
        "product_input_images",
        ["tenant_id", "product_id"],
    )

    enable_rls("product_input_images")
    create_tenant_isolation_policy("product_input_images")
    grant_to_app_role("product_input_images")


def downgrade() -> None:
    op.drop_table("product_input_images")
