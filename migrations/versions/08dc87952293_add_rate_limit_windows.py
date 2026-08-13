"""add rate_limit_windows

Revision ID: 08dc87952293
Revises: 2444ca7c7ac3
Create Date: 2026-08-14 01:45:00.000000

Per-tenant rate limiting (CLAUDE.md §9), Postgres-backed per D19. Same
tenant-scoping reasoning as ``idempotency_keys``'s migration: checked only
from inside an already-authenticated, already-tenant-bound request, so it
gets the ordinary RLS treatment rather than resolver-table status.

``(tenant_id, bucket, window_start)`` is the real business key — one row per
tenant, per named limit, per fixed time window — with the same synthetic
``id`` + ``UNIQUE (tenant_id, id)`` convention applied from the first
migration regardless of whether anything references it yet (``audit_log``'s
precedent). ``count`` has no ``CHECK`` bounding it below ``limit`` at the
schema level — the limit is a per-call parameter to ``RateLimiter.allow``,
not a property of the row, so a single shared table serves every bucket with
whatever limit its caller passes.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role

revision: str = "08dc87952293"
down_revision: str | None = "2444ca7c7ac3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_windows",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("bucket", sa.Text(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_rate_limit_windows_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id", "bucket", "window_start", name="uq_rate_limit_windows_tenant_bucket_window"
        ),
    )
    op.create_index("ix_rate_limit_windows_tenant_id", "rate_limit_windows", ["tenant_id"])

    enable_rls("rate_limit_windows")
    create_tenant_isolation_policy("rate_limit_windows")
    grant_to_app_role("rate_limit_windows")


def downgrade() -> None:
    op.drop_table("rate_limit_windows")
