"""add identity: users, identities, tenant_memberships, platform_admins, sessions

Revision ID: 9e7a9a8cb0f9
Revises: ca5759119d91
Create Date: 2026-08-13 17:10:24.810060

Three of these tables are deliberately global, with no RLS — same reasoning as
``tenants`` in the previous migration:

- ``users`` / ``identities`` — a person's identity is not owned by any one
  tenant; the same person can belong to several.
- ``platform_admins`` — the operator plane sits outside every tenant by
  definition.

``sessions`` is the interesting case. It carries a ``tenant_id`` (the active
tenant, nullable for a platform-plane session with none selected) but is
**not** RLS-protected, for the same resolver reason ``tenant_domains`` was
excluded (see that migration): a refresh-token lookup is how tenant context
gets *established*, so a policy requiring that context to already be set
would make login and refresh impossible. Access to a session is gated by
possession of the high-entropy token whose hash is the lookup key, not by
row-level tenant scoping - the same trust model a password hash table uses.

``tenant_memberships`` looked at first like an ordinary case — "what is this
user's role in this tenant" is tenant-scoped once a session is validated, so
the first draft of this migration gave it full RLS, forced. That was wrong,
and empirically so, not just in theory: with RLS forced, ``softbox_app``
querying with no tenant bound sees zero rows, including this user's own,
because the policy has nothing to compare against. But "which tenants can
this user access at all" — the tenant switcher, and the first thing a login
flow needs before any tenant is chosen — is *exactly* a query with no tenant
bound yet, over a user's own rows across every tenant they belong to. RLS as
designed can only ever answer "rows in the one bound tenant"; it structurally
cannot answer "this user's rows, across all tenants" no matter which
non-superuser role runs it. Confirmed with ``psql`` before reverting this:
``SET ROLE softbox_app`` with no tenant bound reads 0 rows from a table that
demonstrably has rows for that user.

So ``tenant_memberships`` joins ``sessions`` and ``tenant_domains`` as a
tenant-tagged table with **no RLS** — access control is the repository's
explicit ``WHERE tenant_id = ... AND user_id = ...`` (belt-and-braces even
without a policy backing it, per CLAUDE.md's reference pattern), not a row
policy. This is reversible: a future migration could add a second policy
predicate keyed on a separately-bound "current user" GUC to restore
defense-in-depth without losing the cross-tenant query, if this table's
sensitivity later justifies that extra machinery. Not built now — no
consumer needs it yet, and it is not the shape of problem this project's
existing GUC (``app.current_tenant``) solves.

That still leaves ``sessions`` carrying the first genuine **composite
tenant-to-tenant foreign key** (D2), deferred from the previous migration:
``sessions (tenant_id, user_id)`` -> ``tenant_memberships (tenant_id,
user_id)``. A session cannot claim an active tenant the user does not
actually belong to - enforced by Postgres, not application code, and checked
only when ``tenant_id`` is not null (a platform-plane session has nothing to
satisfy). Neither side of this FK carries RLS, so the first instance of the
pattern between two RLS-forced tables is still M4's product_variants ->
products.

``email`` is plain ``text`` with a functional unique index on
``lower(email)`` rather than the ``citext`` the architecture doc's ERD sketch
used - citext needs a Postgres extension, which is another cluster-bootstrap
dependency on every environment for a case-insensitivity feature a functional
index gets for free. The application normalises to lowercase before every
write and lookup.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "9e7a9a8cb0f9"
down_revision: str | None = "ca5759119d91"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    # ── Global tables: no tenant_id, no RLS ─────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("email_verified", sa.Boolean(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    op.create_table(
        "identities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        # `sub` is only unique within one issuer - two Entra tenants, or a
        # provider switching issuers, would otherwise collide.
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("raw_claims", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("provider", "issuer", "subject", name="uq_identities_provider_iss_sub"),
    )
    op.create_index("ix_identities_user_id", "identities", ["user_id"])

    op.create_table(
        "platform_admins",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("granted_by", sa.Uuid(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["granted_by"], ["users.id"]),
    )

    # ── Tenant-scoped, RLS forced ────────────────────────────────────────────
    op.create_table(
        "tenant_memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("extra_capabilities", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tenant_memberships_tenant_id_id"),
        # One role per user per tenant, and the FK target sessions references.
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_id_user_id"),
        sa.CheckConstraint(
            "role IN ('owner','admin','catalog_manager','approver','viewer')",
            name="ck_tenant_memberships_role",
        ),
    )
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    op.create_index("ix_tenant_memberships_user_id", "tenant_memberships", ["user_id"])

    # No RLS - see the module docstring for why this table also turned out
    # to be a resolver table, and how that was found (empirically, not
    # assumed) after the first draft got it wrong.
    grant_to_app_role("tenant_memberships")

    # ── Tenant-tagged resolver table: no RLS (see module docstring) ─────────
    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("refresh_token_hash", sa.Text(), nullable=False),
        # Reuse detection (advisor guidance): a rotated-away token presented
        # again is a replay signal, not a normal failure - the whole session
        # family gets revoked, not just the one call. Nullable: absent on the
        # session created by the original login, before any rotation.
        sa.Column("previous_token_hash", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("refresh_token_hash", name="uq_sessions_refresh_token_hash"),
        # The composite FK this migration's docstring describes: a session's
        # active tenant must be a tenant the user actually belongs to.
        sa.ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.user_id"],
            name="fk_sessions_tenant_membership",
        ),
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"])

    grant_to_app_role("users")
    grant_to_app_role("identities")
    grant_to_app_role("platform_admins")
    grant_to_app_role("sessions")


def downgrade() -> None:
    op.drop_table("sessions")
    op.drop_table("tenant_memberships")
    op.drop_table("platform_admins")
    op.drop_table("identities")
    op.drop_table("users")
