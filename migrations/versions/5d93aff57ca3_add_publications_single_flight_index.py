"""add publications single-flight index

Revision ID: 5d93aff57ca3
Revises: e37248aeeee4
Create Date: 2026-08-15 04:20:00.000000

D21's single-flight requirement: "a single-flight lock per (account,
variant)". A Postgres advisory lock does not fit this codebase's UoW
shape — `SqlUnitOfWork.__aenter__` opens a fresh session (and therefore a
fresh physical connection) per `async with` block, and `PublishChannelAgent`
spans three independent transactions (`Start`, then `Complete`/`Fail`/
`Defer`) across one logical attempt. A session-scoped advisory lock taken
in `Start`'s transaction would be unreachable from the connection that
later runs `Complete`; a transaction-scoped one would release the instant
`Start` commits, long before the provider call it is meant to guard.

So the guard is a **partial unique index**, the same "live row" primitive
`catalog_images` already uses (`ix_catalog_images_live_per_variant_slot`),
applied to the two states in which a `Publication` is actively in flight
rather than done. Two publications for the same `(channel_id, variant_id)`
can coexist once the first has reached a terminal state (`published` or
`failed`) — re-publishing a variant to a channel it was already posted to,
or retrying after a dead-letter with a fresh row, are both legitimate.
What must never coexist is two rows both still trying.

`CreatePublication` pre-checks via `PublicationRepository.get_live` for a
clean `ConflictError` in the common case; this index is the backstop for
the check-then-act race between two concurrent `CreatePublication` calls,
exactly the shape D15's `uq_category_spec_versions_tenant_category_version`
already established for a different table (see that migration's docstring
and `tests/infrastructure/test_category_spec_version_uniqueness.py`).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5d93aff57ca3"
down_revision: str | None = "e37248aeeee4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_publications_live_per_channel_variant",
        "publications",
        ["tenant_id", "channel_id", "variant_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'publishing')"),
    )


def downgrade() -> None:
    op.drop_index("ix_publications_live_per_channel_variant", table_name="publications")
