"""add catalog_images

Revision ID: c9e1a3f5b7d2
Revises: b6d8f2a4c1e9
Create Date: 2026-08-14 18:00:00.000000

The current-state row per (variant, catalog slot) (D18) — mutable
approval/QC state, unlike the immutable `generation_items` attempt log.
`generation_item_id` is a composite FK to the winning attempt.

The partial unique index is the correctness-critical piece: it permits
exactly one **live** row per (variant, slot) while retaining full history.
Regeneration sets `superseded_by` on the existing live row and inserts the
replacement **in one transaction**, and the two constraints on this table
pull the write order in opposite directions unless one of them is deferred:

- The partial unique index (never deferrable in Postgres — only a full,
  non-partial unique constraint can be) is checked at the end of each
  statement. It forces `UPDATE` (retire the old row) **before** `INSERT`
  (add the replacement) — inserting first leaves two rows live at once.
- The self-referential FK on `superseded_by` forces the opposite order on
  its own: the old row's `UPDATE` can only reference a replacement row that
  already exists, which means `INSERT` **before** `UPDATE`.

Both cannot go first, so `fk_catalog_images_superseded_by` is
`DEFERRABLE INITIALLY DEFERRED` (a real Postgres FK feature; there is no
deferrable *partial* unique index to lean on instead). That makes the
correct order `UPDATE` (retire the old row, referencing a not-yet-existing
replacement — legal, because the FK isn't checked until commit) **then**
`INSERT` (add the replacement, satisfying both the now-checked-immediately
unique index and, at commit, the deferred FK). Written the other way round
— `INSERT` before `UPDATE` — the unique index rejects the `INSERT`
immediately, before the FK is ever reached. See
`entities.catalog_image`'s module docstring and
`tests/infrastructure/test_catalog_image_supersede.py`, which proves both
orderings against real Postgres — including that the wrong order was
initially assumed and caught by the test actually failing with a **foreign
key** violation, not the unique violation expected, which is what surfaced
this constraint-interaction bug in the first place.

`superseded_by` is a **self-referential** composite FK
(`(tenant_id, id) -> catalog_images(tenant_id, id)`), the first
self-reference in this schema — needs no special handling beyond the same
`UNIQUE(tenant_id, id)` every other tenant-scoped table already carries.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "c9e1a3f5b7d2"
down_revision: str | None = "b6d8f2a4c1e9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_STATUSES = ("pending_qc", "qc_failed", "human_review", "pending_approval", "approved", "rejected")


def upgrade() -> None:
    op.create_table(
        "catalog_images",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_image_slot_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("generation_item_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("qc_result", postgresql.JSONB(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_catalog_images_variant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "catalog_image_slot_id"],
            ["catalog_image_slots.tenant_id", "catalog_image_slots.id"],
            name="fk_catalog_images_slot",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "asset_id"],
            ["assets.tenant_id", "assets.id"],
            name="fk_catalog_images_asset",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "generation_item_id"],
            ["generation_items.tenant_id", "generation_items.id"],
            name="fk_catalog_images_generation_item",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "superseded_by"],
            ["catalog_images.tenant_id", "catalog_images.id"],
            name="fk_catalog_images_superseded_by",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["users.id"],
            name="fk_catalog_images_approved_by",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_images_tenant_id_id"),
        sa.CheckConstraint(
            "status IN ('" + "','".join(_STATUSES) + "')",
            name="ck_catalog_images_status",
        ),
    )
    op.create_index("ix_catalog_images_tenant_id", "catalog_images", ["tenant_id"])
    op.create_index(
        "ix_catalog_images_live_per_variant_slot",
        "catalog_images",
        ["tenant_id", "variant_id", "catalog_image_slot_id"],
        unique=True,
        postgresql_where=sa.text("superseded_by IS NULL"),
    )

    enable_rls("catalog_images")
    create_tenant_isolation_policy("catalog_images")
    grant_to_app_role("catalog_images")


def downgrade() -> None:
    op.drop_table("catalog_images")
