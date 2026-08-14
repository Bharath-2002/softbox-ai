"""add task_queue_jobs

Revision ID: e9f3a7c5b2d4
Revises: c2b8e4f6a1d7
Create Date: 2026-08-14 14:00:00.000000

The Postgres-backed queue D19 chose over Redis for v1: `SELECT ... FOR
UPDATE SKIP LOCKED` claims one job, atomically, in the same statement as
the state transition to `running` (see `SqlTaskQueue.claim` — a two-step
"lock then update" would be the check-then-act bug D24 already warns
against, in a different costume).

Four states only (`pending`, `running`, `succeeded`, `dead`) — no separate
transient `failed` status. A failed attempt with retries remaining goes
straight back to `pending` with a later `run_at` (the backoff), so `failed`
would only ever be observed for an instant before the next transition;
`dead` is the durable "no more retries" terminus D19 requires.

`claim()` is tenant-scoped, like every other port in this codebase (D9) —
not a cross-tenant sweep. That is a deliberate, bounded tradeoff, not an
oversight: RLS is FORCED here exactly like every other tenant-scoped table,
and the app role holds no BYPASSRLS, so an unscoped claim query would see
zero rows regardless of which tenant a job belongs to — there is no way to
express "the next claimable job across every tenant" without either a new
bypass role (a security-sensitive decision nothing here asked for) or a
worker that loops the tenant list and claims per tenant. The latter is what
this schema assumes; revisit if this ever becomes a contention hotspot
(D19's own named trigger for reconsidering the queue design).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "e9f3a7c5b2d4"
down_revision: str | None = "c2b8e4f6a1d7"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_queue_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_task_queue_jobs_tenant_id_id"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'succeeded', 'dead')",
            name="ck_task_queue_jobs_status",
        ),
    )
    op.create_index("ix_task_queue_jobs_tenant_id", "task_queue_jobs", ["tenant_id"])
    # The exact predicate `claim()` filters on - a pending job due to run.
    op.create_index(
        "ix_task_queue_jobs_claimable",
        "task_queue_jobs",
        ["tenant_id", "run_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    enable_rls("task_queue_jobs")
    create_tenant_isolation_policy("task_queue_jobs")
    grant_to_app_role("task_queue_jobs")


def downgrade() -> None:
    op.drop_table("task_queue_jobs")
