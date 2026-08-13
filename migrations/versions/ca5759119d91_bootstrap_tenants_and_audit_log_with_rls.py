"""bootstrap tenants and audit_log with RLS

Revision ID: ca5759119d91
Revises:
Create Date: 2026-08-13 16:02:45.407496

Establishes the schema's root and proves the tenant-isolation mechanism (D3)
end to end with one real, RLS-protected table.

``tenants`` deliberately carries no RLS: it is the root of the hierarchy, not
a tenant-scoped table — there is no ``tenant_id`` column to filter on, and the
platform plane (D4) needs to read across every tenant. Access to a tenant's
own row is an application-layer authorization concern (capability check
against the authenticated principal), not a row-level policy.

``audit_log`` is the table that proves the pattern: genuinely tenant-scoped,
genuinely sensitive (before/after state of every mutation), no legitimate
cross-tenant read path for the non-owner application role. ``actor_user_id``
is a bare UUID column for now rather than a foreign key — ``users`` does not
exist yet (Identity & tenancy is its own later chunk). Adding that constraint
later is an additive migration, not a breaking one.

No composite tenant-to-tenant foreign key (D2) appears in this migration —
none of the tables introduced here reference another tenant-scoped table, so
there is nothing yet to make composite. The pattern is proven for real once
one exists, starting with product_variants -> products in M4.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "ca5759119d91"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False, unique=True),
        # No default: every insert states its status explicitly rather than
        # relying on a value that would otherwise be invisible in the row.
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("plan", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("before", postgresql.JSONB(), nullable=True),
        sa.Column("after", postgresql.JSONB(), nullable=True),
        sa.Column("ip", postgresql.INET(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        # UNIQUE(tenant_id, id) even with no composite FK referencing this
        # table yet (D2) — the convention applies from a tenant-scoped
        # table's first migration, not retrofitted once something needs it.
        sa.UniqueConstraint("tenant_id", "id", name="uq_audit_log_tenant_id_id"),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])
    op.create_index("ix_audit_log_tenant_occurred", "audit_log", ["tenant_id", "occurred_at"])

    enable_rls("audit_log")
    create_tenant_isolation_policy("audit_log")
    grant_to_app_role("audit_log")

    # tenants has no RLS (see module docstring), but the app role still needs
    # ordinary access to it, gated by explicit WHERE clauses in application
    # code rather than a policy.
    grant_to_app_role("tenants")


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("tenants")
