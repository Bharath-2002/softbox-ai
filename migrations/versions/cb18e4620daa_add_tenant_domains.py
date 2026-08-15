"""add tenant domains

Revision ID: cb18e4620daa
Revises: f19bde677376
Create Date: 2026-08-15 09:31:32.377814

`tenant_domains` resolves a storefront request's tenant from its Host header
(D4, docs/DIAGRAMS.md 5a) — the same "no tenant known yet" shape as
`sessions`/`tenant_memberships` (see 9e7a9a8cb0f9's module docstring): a
policy requiring `app.current_tenant` to already be set would make the very
lookup that establishes it impossible. No RLS here, for the identical reason
and the identical fix — access control is `SqlTenantDomainRepository`'s
explicit `WHERE` clauses, not a row policy. `resolve_by_hostname` filters by
`hostname` alone (no tenant to filter by yet); every other method filters by
`tenant_id` explicitly regardless of the missing policy, per CLAUDE.md's "the
filter is the only thing that does, so it is never optional."

`hostname` is globally unique, not per-tenant — two tenants cannot claim the
same Host header, so the constraint is a bare `UNIQUE (hostname)` rather than
`UNIQUE (tenant_id, hostname)`. `UNIQUE (tenant_id, id)` is still added for
convention (CLAUDE.md's composite-FK pattern), even though no other table
references this one yet.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import grant_to_app_role

revision: str = "cb18e4620daa"
down_revision: str | None = "f19bde677376"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_domains",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("hostname", sa.Text(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tenant_domains_tenant_id_id"),
        sa.UniqueConstraint("hostname", name="uq_tenant_domains_hostname"),
    )
    op.create_index("ix_tenant_domains_tenant_id", "tenant_domains", ["tenant_id"])

    # No RLS - see module docstring.
    grant_to_app_role("tenant_domains")


def downgrade() -> None:
    op.drop_table("tenant_domains")
