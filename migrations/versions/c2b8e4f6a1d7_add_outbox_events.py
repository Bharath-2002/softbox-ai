"""add outbox_events

Revision ID: c2b8e4f6a1d7
Revises: a7d3e5c9f1b8
Create Date: 2026-08-14 13:00:00.000000

The transactional outbox (D19, M5 chunk 1): a domain event is written to
this table in the **same transaction** as the state change it describes, so
there is never a "committed but never enqueued" gap between a use case's
commit and a later relay picking the event up. No `event` domain object
maps here — same shape as `idempotency_keys`/`platform_admins`: "a stored
delivery ticket, not a rich domain object" (see `mapping.py`'s comment on
those tables), queried via Core directly by `SqlOutboxEventRepository`.

The partial index on `published_at IS NULL` is the exact shape a relay
queries: "give me this tenant's unpublished events, oldest first" — an
ordinary index would also work but would carry every already-published row
forever, growing unboundedly relative to the useful (unpublished) subset.

No FK from `payload` to whatever it describes — deliberately. An outbox
event is a fact about something that already happened, serialized once; if
the row it references is later deleted, the event should still be
replayable/auditable, not blocked by a dangling FK or cascade-deleted with
its subject.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "c2b8e4f6a1d7"
down_revision: str | None = "a7d3e5c9f1b8"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_outbox_events_tenant_id_id"),
    )
    op.create_index("ix_outbox_events_tenant_id", "outbox_events", ["tenant_id"])
    op.create_index(
        "ix_outbox_events_unpublished",
        "outbox_events",
        ["tenant_id", "created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )

    enable_rls("outbox_events")
    create_tenant_isolation_policy("outbox_events")
    grant_to_app_role("outbox_events")


def downgrade() -> None:
    op.drop_table("outbox_events")
