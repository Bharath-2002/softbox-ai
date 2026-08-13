"""add idempotency_keys

Revision ID: 2444ca7c7ac3
Revises: 9e7a9a8cb0f9
Create Date: 2026-08-14 01:06:43.858412

Genuinely tenant-scoped, and unlike ``sessions`` / ``tenant_domains`` /
``tenant_memberships`` it is not a resolver table — idempotency is only ever
checked from inside an already-authenticated, already-tenant-bound request,
so there is no "establish context" chicken-and-egg problem here. Gets the
ordinary RLS treatment (D3): ``ENABLE``, ``FORCE``, and the standard
isolation policy, same as ``audit_log``.

Carries a synthetic ``id`` plus ``UNIQUE (tenant_id, id)`` even though
nothing references this table via a composite FK yet, per the convention
``audit_log``'s migration established: apply it from a tenant-scoped table's
first migration, not retrofitted once something needs it. The actual
business key is the separate ``UNIQUE (tenant_id, key)``, which is what
``reserve()``'s ``ON CONFLICT`` targets.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "2444ca7c7ac3"
down_revision: str | None = "9e7a9a8cb0f9"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("request_fingerprint", sa.Text(), nullable=False),
        # Both null between reserve() and store_response() - the in-flight
        # state is legitimate and distinguishable, not an error (see the
        # port's module docstring).
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_idempotency_keys_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_idempotency_keys_tenant_id_key"),
    )
    op.create_index("ix_idempotency_keys_tenant_id", "idempotency_keys", ["tenant_id"])

    enable_rls("idempotency_keys")
    create_tenant_isolation_policy("idempotency_keys")
    grant_to_app_role("idempotency_keys")


def downgrade() -> None:
    op.drop_table("idempotency_keys")
