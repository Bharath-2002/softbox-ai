"""add quota_reservations

Revision ID: f7a1c9e3d5b6
Revises: e9f3a7c5b2d4
Create Date: 2026-08-14 15:00:00.000000

Atomic quota reservation (D24). The row for `(tenant_id, period, metric)`
must already exist before `reserve()` can succeed — `reserve()` is a plain
`UPDATE`, which affects zero rows against a metric nobody has provisioned a
limit for yet, and zero rows is treated identically to "over quota" by the
port (see its module docstring for why that fail-closed default, not
fail-open, is the correct one). `ensure_period` is the provisioning step,
called separately.

`reserved` is the live total that must never exceed `limit_value` — bumped
by `reserve()`, given back by `release()` on terminal failure. `committed`
is a separate, monotonically-increasing counter for "how much has actually
been consumed" (reporting/audit), untouched by `release()`. Both start at 0
and are always supplied explicitly by the adapter, never a DB-level
default, matching this codebase's "no invisible-in-the-row default" rule
for a column whose value materially changes meaning (`audit_log`'s
migration sets the same precedent for `status`).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role

revision: str = "f7a1c9e3d5b6"
down_revision: str | None = "e9f3a7c5b2d4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "quota_reservations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("period", sa.Text(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("limit_value", sa.Integer(), nullable=False),
        sa.Column("reserved", sa.Integer(), nullable=False),
        sa.Column("committed", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_quota_reservations_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id", "period", "metric", name="uq_quota_reservations_tenant_period_metric"
        ),
        sa.CheckConstraint("reserved >= 0", name="ck_quota_reservations_reserved_non_negative"),
        sa.CheckConstraint("committed >= 0", name="ck_quota_reservations_committed_non_negative"),
        sa.CheckConstraint(
            "reserved <= limit_value", name="ck_quota_reservations_reserved_within_limit"
        ),
    )
    op.create_index("ix_quota_reservations_tenant_id", "quota_reservations", ["tenant_id"])

    enable_rls("quota_reservations")
    create_tenant_isolation_policy("quota_reservations")
    grant_to_app_role("quota_reservations")


def downgrade() -> None:
    op.drop_table("quota_reservations")
