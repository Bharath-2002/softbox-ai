"""add generation_items

Revision ID: b6d8f2a4c1e9
Revises: a3c7e1f9b4d6
Create Date: 2026-08-14 17:00:00.000000

The immutable per-attempt record (D18): one row per attempt at rendering one
`catalog_image_slot` for one `generation_request`. `attempt_no` distinguishes
retries — a retry creates a **new** row, never updates a failed one in
place, which is what makes this the lineage/audit table `catalog_images`
(next) is not.

`input_asset_ids` is a Postgres `uuid[]` column, this schema's first array
column — a fixed, small, ordered list read once when composing the prompt,
not a relation queried on its own, so a join table would add write-side
complexity for no read-side benefit. Postgres cannot enforce a foreign key
on array elements, so referential integrity on this column is an
application-level concern, not a database one; documented here rather than
silently assumed.

`output_asset_id` is nullable (only known once the attempt succeeds) and a
composite FK to `assets`, same as every other asset reference in this
schema.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "b6d8f2a4c1e9"
down_revision: str | None = "a3c7e1f9b4d6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_STATUSES = ("pending", "running", "succeeded", "failed", "dead")


def upgrade() -> None:
    op.create_table(
        "generation_items",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("request_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_image_slot_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("model_params", postgresql.JSONB(), nullable=False),
        sa.Column("seed", sa.BigInteger(), nullable=False),
        sa.Column("prompt_rendered", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("input_asset_ids", postgresql.ARRAY(sa.Uuid()), nullable=False),
        sa.Column("output_asset_id", sa.Uuid(), nullable=True),
        sa.Column("cost_micros", sa.BigInteger(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "request_id"],
            ["generation_requests.tenant_id", "generation_requests.id"],
            name="fk_generation_items_request",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "catalog_image_slot_id"],
            ["catalog_image_slots.tenant_id", "catalog_image_slots.id"],
            name="fk_generation_items_slot",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "template_id"],
            ["catalog_templates.tenant_id", "catalog_templates.id"],
            name="fk_generation_items_template",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "output_asset_id"],
            ["assets.tenant_id", "assets.id"],
            name="fk_generation_items_output_asset",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_generation_items_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "request_id",
            "catalog_image_slot_id",
            "attempt_no",
            name="uq_generation_items_request_slot_attempt",
        ),
        sa.CheckConstraint(
            "status IN ('" + "','".join(_STATUSES) + "')",
            name="ck_generation_items_status",
        ),
    )
    op.create_index("ix_generation_items_tenant_id", "generation_items", ["tenant_id"])
    op.create_index(
        "ix_generation_items_tenant_request",
        "generation_items",
        ["tenant_id", "request_id"],
    )

    enable_rls("generation_items")
    create_tenant_isolation_policy("generation_items")
    grant_to_app_role("generation_items")


def downgrade() -> None:
    op.drop_table("generation_items")
