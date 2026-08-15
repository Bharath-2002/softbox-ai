"""add publication metrics

Revision ID: f19bde677376
Revises: e563d43d40b4
Create Date: 2026-08-15 09:00:00.000000

D21's `fetch_metrics` port method has had no caller since it was written —
`docs/DIAGRAMS.md`'s own ERD already names the column (`jsonb metrics
"fetched back later"`), unlike D17's renditions, which needed a real
adapter's `ChannelCapabilities` to know their target shape at all.
`ChannelMetrics(impressions, likes, clicks)` is fully specified regardless
of which real adapter eventually exists, so this is buildable now,
fake-backed, the same posture every other D21 piece has had all along.

`metrics_fetched_at` is not in the diagram's ERD (which omits `created_at`/
`updated_at` too, the same simplified-view convention) but is needed to
avoid re-fetching a row that was just refreshed — the same "avoid
re-selecting on the next sweep" concern `due_at`'s `_DISPATCH_GRACE` guard
solves for the publish path, applied here to a staleness window instead of
a fixed grace period, since metrics fetching is a repeating refresh, not a
one-shot attempt. Also doubles as the claim signal:
`StartPublicationMetricsFetch` bumps it the moment a row is selected, not
only after a successful fetch, so a provider failure doesn't cause an
immediate re-select loop on the same row within one sweep.

Both columns nullable, no CHECK, no index — nothing queries `metrics`
itself yet (no read endpoint), and `metrics_fetched_at` only needs the
same `SKIP LOCKED` scan `list_due_for_release` already established, not a
dedicated index at this row count.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f19bde677376"
down_revision: str | None = "e563d43d40b4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("publications", sa.Column("metrics", postgresql.JSONB(), nullable=True))
    op.add_column(
        "publications",
        sa.Column("metrics_fetched_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("publications", "metrics_fetched_at")
    op.drop_column("publications", "metrics")
