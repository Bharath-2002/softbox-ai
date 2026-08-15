"""rework publications state machine to match docs/DIAGRAMS.md

Revision ID: e563d43d40b4
Revises: 6e9ce80dab43
Create Date: 2026-08-15 07:00:00.000000

The previous two migrations (`5d93aff57ca3`, `6e9ce80dab43`) built
`publications` from D21's prose sketch in `docs/ARCHITECTURE.md` alone,
without checking `docs/DIAGRAMS.md`'s own ERD and state diagram for
`Publication` — a real process gap, since CLAUDE.md lists `DIAGRAMS.md` as
required reading for exactly this ("flows, state machines, schema"). The
diagram specifies a different column name and a different, more complete
status vocabulary than what shipped. Caught before any more was built on
top (the D17 rendition-linking work), reconciled here rather than left to
drift further — user confirmed reworking toward the diagram over keeping
the shipped shape.

**Column rename**: `scheduled_at` -> `due_at`, matching both the diagram's
ERD and D21's own prose ("scheduling is a `due_at` column plus a poller").
No production data exists anywhere this codebase has been deployed, so a
straight `ALTER COLUMN` rename in one migration is the honest choice here,
not an evasion of the expand/contract rule — that rule protects a rolling
deploy where old code (referencing the old column) might still run against
the new schema, a scenario that cannot happen for a codebase with a single
environment and no live traffic. Also widens `due_at` to `NOT NULL`: every
publication now always has a due time (immediate creates default it to
`now`, see `entities.publication.Publication.create`), where the old
`scheduled_at` was optional and meant "no schedule." Any pre-existing NULL
is backfilled to `created_at` before the `NOT NULL` is added, defensively
— no such row is expected to exist, but the migration must not fail if one
somehow does.

**Status vocabulary**, replacing the previous five-value set entirely with
the diagram's six (`scheduled dispatching published failed dead
cancelled`):
- `scheduled` (was `pending`/`scheduled` collapsed) — every publication
  starts here; the sole exit conditions are the `due_at` poller finding it
  due, or an explicit cancel.
- `dispatching` (was `publishing`) — a `ChannelPublisher` call is
  in flight or about to be.
- `published` — unchanged.
- `failed` (was collapsed into `pending`) — a **transient**, retryable
  attempt failure, its own named state now rather than folded back into
  "not yet tried." The previous design's docstring argued explicitly for
  the collapse; the diagram disagrees, and the diagram is the more
  detailed source once actually read. `failed -> dispatching` is the
  retry edge, driven by `TaskQueue`'s own backoff-rescheduled job, not by
  the `due_at` poller — a retry never goes back through `scheduled`.
- `dead` (was `failed`) — terminal, retry budget exhausted.
- `cancelled` (new) — `scheduled -> cancelled` only; see
  `features.publishing.cancel_publication`, built in this same commit so
  the state has a real caller (the same "don't ship a lying state" bar
  `c531cb8` set for `content_drafts.generated`).

**Single-flight index** (`ix_publications_live_per_channel_variant`,
added one migration before this) widens its predicate from
`('scheduled', 'pending', 'publishing')` to `('scheduled', 'dispatching',
'failed')` — `failed` is a retryable, still-in-flight attempt and must
still block a second concurrent publish for the same channel and variant;
`dead`/`published`/`cancelled` are all terminal and correctly do not.

Both changes are one semantic unit — the status rename and the index's
live-set both describe "what does in-flight mean for this table" — so
this stays a single migration rather than an artificial split.

**Downgrade only succeeds on a database with no rows in the new-only
statuses** (`dispatching`, `failed`, `dead`, `cancelled`) or a NULL
`due_at` would be impossible to reconstruct — same narrowing-check hazard
verified by hand for `6e9ce80dab43` and `e88d14230ad4`, verified the same
way here: inserted a `cancelled` row, ran `alembic downgrade -1`, confirmed
Postgres rejects it with a check violation, then cleaned up and
re-verified the downgrade succeeds against an empty table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e563d43d40b4"
down_revision: str | None = "6e9ce80dab43"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_OLD_STATUSES = ("scheduled", "pending", "publishing", "published", "failed")
_NEW_STATUSES = ("scheduled", "dispatching", "published", "failed", "dead", "cancelled")
_INDEX_NAME = "ix_publications_live_per_channel_variant"
_OLD_LIVE = ("scheduled", "pending", "publishing")
_NEW_LIVE = ("scheduled", "dispatching", "failed")


def upgrade() -> None:
    # FORCE ROW LEVEL SECURITY (D3) binds even this migration's owner
    # connection to the tenant-isolation policy, so a cross-tenant backfill
    # UPDATE with no `app.current_tenant` set would silently match zero
    # rows. Lifted only for this one statement, restored immediately after
    # — the standard, Postgres-documented way for a table owner to run an
    # administrative statement across all tenants.
    op.execute("ALTER TABLE publications NO FORCE ROW LEVEL SECURITY")
    op.execute("UPDATE publications SET scheduled_at = created_at WHERE scheduled_at IS NULL")
    op.execute("ALTER TABLE publications FORCE ROW LEVEL SECURITY")
    op.alter_column("publications", "scheduled_at", new_column_name="due_at", nullable=False)

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
        postgresql_where=sa.text("status IN ('" + "', '".join(_NEW_LIVE) + "')"),
    )


def downgrade() -> None:
    op.drop_index(_INDEX_NAME, table_name="publications")
    op.create_index(
        _INDEX_NAME,
        "publications",
        ["tenant_id", "channel_id", "variant_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('" + "', '".join(_OLD_LIVE) + "')"),
    )

    op.drop_constraint("ck_publications_status", "publications", type_="check")
    op.create_check_constraint(
        "ck_publications_status",
        "publications",
        "status IN ('" + "','".join(_OLD_STATUSES) + "')",
    )

    op.alter_column("publications", "due_at", new_column_name="scheduled_at", nullable=True)
