"""add social accounts

Revision ID: 2daa149ded1f
Revises: e88d14230ad4
Create Date: 2026-08-15 01:23:25.027805

Storage layer only (D21/D22) — the connected-account row a `publications`
row's `channel_id` will reference, built ahead of `publications` purely so
that FK target exists; **no OAuth connect flow, no token refresh, no
envelope encryption lands in this chunk**. That is a deliberate split, not
an oversight: none of those need this table's shape decided first, and
guessing at the OAuth state machine (what counts as "connecting", what a
mid-flow row looks like) before a real provider-facing chunk needs it
would repeat the `workflow_runs`/`content_drafts` speculative-generic
mistake this project has already been burned by twice.

`status` ships with a single value, `connected`, for the same reason
`content_drafts.status` originally shipped with only `generated`: nothing
in this chunk drives a transition, so there is nothing to validate a wider
vocabulary against yet. The OAuth-connect chunk widens this `CHECK`
constraint via a normal expand migration when it has a real state machine
to encode (`token_expired`, `revoked`, `error` are the obvious candidates,
not committed to here).

`credentials_encrypted`/`encryption_key_id` are real, nullable columns
from day one even though nothing writes to them yet — D22's rotation
story depends on `encryption_key_id` existing per row from the start, not
being bolted on once a second key is in play. Nullable because this
chunk's storage layer has no encryption adapter to populate them with; a
row cannot represent "connected" and "has no credentials" as a state
machine, so nullability here is honestly "not built yet," not a real
domain state.

`UNIQUE (tenant_id, provider, external_account_id)` — connecting the same
provider account twice for one tenant is a duplicate, not a second
account; this is the one invariant this chunk's schema can enforce
without any OAuth logic to drive it.

Accepted, not fixed: this chunk's own test data creates rows with
`status = 'connected'` and `credentials_encrypted IS NULL`, which means a
later `CHECK (status <> 'connected' OR credentials_encrypted IS NOT NULL)`
cannot be added as a bare expand migration — it would reject rows this
chunk itself produced. The OAuth-connect chunk either backfills before
adding that constraint or accepts enforcing "connected implies has
credentials" at the application layer instead of the database's. Deciding
which is that chunk's job, not this one's — named here so it is a known
tradeoff, not a surprise.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role

revision: str = "2daa149ded1f"
down_revision: str | None = "e88d14230ad4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_STATUSES = ("connected",)


def upgrade() -> None:
    op.create_table(
        "social_accounts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_account_id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("credentials_encrypted", sa.LargeBinary(), nullable=True),
        sa.Column("encryption_key_id", sa.Text(), nullable=True),
        sa.Column("scopes", sa.ARRAY(sa.Text()), nullable=False),
        sa.Column("access_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refresh_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_social_accounts_tenant", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_social_accounts_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "external_account_id",
            name="uq_social_accounts_tenant_provider_account",
        ),
        sa.CheckConstraint(
            "status IN ('" + "','".join(_STATUSES) + "')",
            name="ck_social_accounts_status",
        ),
    )
    op.create_index("ix_social_accounts_tenant_id", "social_accounts", ["tenant_id"])

    enable_rls("social_accounts")
    create_tenant_isolation_policy("social_accounts")
    grant_to_app_role("social_accounts")


def downgrade() -> None:
    op.drop_table("social_accounts")
