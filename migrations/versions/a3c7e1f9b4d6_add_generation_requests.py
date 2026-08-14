"""add generation_requests

Revision ID: a3c7e1f9b4d6
Revises: f7a1c9e3d5b6
Create Date: 2026-08-14 16:00:00.000000

The run-level row for one "Save & Generate" (D18, D19): one per product
variant, fanning out into many `generation_items` (not yet built — the next
chunk). `spec_version_id` is the pinned snapshot the request was generated
against, same D15 discipline as `products`/`product_variants` — a later spec
change must never retroactively alter what an in-flight or historical
request meant.

`quota_reservation_id` is nullable-at-the-type-level but always set before a
request leaves `queued` in practice: `CreateGenerationRequest` reserves
quota first (D24, `quota_reservations.reserve()`), and only enqueues if that
succeeds. It is a composite FK to `quota_reservations(tenant_id, id)`, not
`(tenant_id, period, metric)` — `reserve()` itself only returns a bool, so
the use case that writes this column must fetch the row's `id` via
`quota_reservations.get()` after a successful reserve.

`settings_snapshot` carries whatever generation-time settings (model
choice, per-request overrides) applied, for the same reproducibility reason
`generation_items` (next chunk) records model/prompt_version/seed per
attempt.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "a3c7e1f9b4d6"
down_revision: str | None = "f7a1c9e3d5b6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_STATUSES = ("queued", "running", "succeeded", "partially_failed", "failed", "cancelled")


def upgrade() -> None:
    op.create_table(
        "generation_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("spec_version_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("settings_snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("quota_reservation_id", sa.Uuid(), nullable=True),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_generation_requests_product",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_generation_requests_variant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "spec_version_id"],
            ["category_spec_versions.tenant_id", "category_spec_versions.id"],
            name="fk_generation_requests_spec_version",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "quota_reservation_id"],
            ["quota_reservations.tenant_id", "quota_reservations.id"],
            name="fk_generation_requests_quota_reservation",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name="fk_generation_requests_requested_by",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_generation_requests_tenant_id_id"),
        sa.CheckConstraint(
            "status IN ('" + "','".join(_STATUSES) + "')",
            name="ck_generation_requests_status",
        ),
    )
    op.create_index("ix_generation_requests_tenant_id", "generation_requests", ["tenant_id"])
    op.create_index(
        "ix_generation_requests_tenant_variant",
        "generation_requests",
        ["tenant_id", "variant_id"],
    )

    enable_rls("generation_requests")
    create_tenant_isolation_policy("generation_requests")
    grant_to_app_role("generation_requests")


def downgrade() -> None:
    op.drop_table("generation_requests")
