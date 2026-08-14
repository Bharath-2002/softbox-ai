"""widen publications status for scheduling

Revision ID: 6e9ce80dab43
Revises: 5d93aff57ca3
Create Date: 2026-08-15 05:30:00.000000

Expand migration (CLAUDE.md §8) adding `scheduled` to `ck_publications_status`
— D21's "scheduling is a `due_at` column plus a poller, a task queue does
not schedule reliably across restarts and redeploys." `scheduled_at` has
existed on this table since its first migration but had no writer that
distinguished "publish now" from "publish later"; every `Publication` sat
in `PENDING` regardless. A `Publication` created with a future
`scheduled_at` now starts in `SCHEDULED` instead, and
`features.publishing.release_scheduled_publications` moves it to `PENDING`
(and writes its `publish_requested` outbox event) once due — see
`entities.publication`'s own docstring for the state's full role.

`ix_publications_live_per_channel_variant` (the single-flight guard added
one migration ago) must widen its predicate the same way: a `SCHEDULED`
publication is exactly as "live" as a `PENDING`/`PUBLISHING` one for that
guard's purpose — a second create for the same channel and variant must
not slip in just because the first is waiting for its scheduled time
rather than actively retrying. Postgres cannot `ALTER` a partial index's
predicate in place, so this drops and recreates it in the same migration
as the status widening, since the two changes are only meaningful together
(a `SCHEDULED` row the index doesn't cover would defeat the guard the
moment scheduling has a real writer).

**Downgrade only succeeds on a database with no `scheduled` rows** — same
narrowing-check hazard as `e88d14230ad4_widen_content_draft_status`,
verified by hand the same way: inserted a `scheduled` row, ran
`alembic downgrade -1`, confirmed Postgres rejects it with a check
violation, then cleaned up and re-verified the downgrade succeeds against
an empty table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6e9ce80dab43"
down_revision: str | None = "5d93aff57ca3"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_OLD_STATUSES = ("pending", "publishing", "published", "failed")
_NEW_STATUSES = ("scheduled", "pending", "publishing", "published", "failed")
_INDEX_NAME = "ix_publications_live_per_channel_variant"


def upgrade() -> None:
    op.drop_constraint("ck_publications_status", "publications", type_="check")
    op.create_check_constraint(
        "ck_publications_status",
        "publications",
        "status IN ('" + "','".join(_NEW_STATUSES) + "')",
    )
    op.drop_index(_INDEX_NAME, table_name="publications")
    op.create_index(
        _INDEX_NAME,
        "publications",
        ["tenant_id", "channel_id", "variant_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('scheduled', 'pending', 'publishing')"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="publications")
    op.create_index(
        _INDEX_NAME,
        "publications",
        ["tenant_id", "channel_id", "variant_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'publishing')"),
    )
    op.drop_constraint("ck_publications_status", "publications", type_="check")
    op.create_check_constraint(
        "ck_publications_status",
        "publications",
        "status IN ('" + "','".join(_OLD_STATUSES) + "')",
    )
