"""widen content_drafts status to include the approval gate

Revision ID: e88d14230ad4
Revises: 28b3907984f5
Create Date: 2026-08-16 09:00:00.000000

Expand migration (CLAUDE.md §8) widening `ck_content_drafts_status` from
the single `generated` member the storage-layer chunk (28b3907984f5)
deliberately shipped with — see that migration's own docstring, and
`entities.content_draft`'s, for why guessing the full vocabulary early
would have repeated the `workflow_runs` speculative-generic mistake.

Also adds `rejection_reason TEXT NULL`, `approved_by UUID NULL` (FK
`users(id)`, unqualified by `tenant_id` — same shape as
`catalog_images.approved_by`, since `users` is not itself tenant-scoped)
and `approved_at TIMESTAMPTZ NULL` — `catalog_images` records all three on
approve/reject and M6's own gate bullet ("reject with a reason") applies to
copy exactly as it does to imagery; all nullable, so this is a plain expand
with no backfill concern.

Adds `pending_approval`, `approved`, `rejected` — **not** a collapse of
`generated` into "awaiting approval." `catalog_images` never collapsed
`pending_qc`/`pending_approval` into one value, and the same reason applies
here: a state a human is meant to act on needs its own name, so nothing
else (a future "manual copy editing" chunk's initial status, for one) can
accidentally land there by sharing a value that meant something else.
`generated` stays what `ContentDraft.create()` produces; a new
`mark_pending_approval()` moves it to `pending_approval` in the same
transaction, mirroring `mark_qc_passed`'s role for `catalog_images`.

**Downgrade only succeeds on a database with no `approved`/`rejected`/
`pending_approval` rows** — narrowing a `CHECK` constraint while live data
uses the wider vocabulary is exactly the "destructive contraction" D8
warns against, so `ALTER TABLE ... ADD CONSTRAINT` correctly fails loudly
in that case rather than silently orphaning rows against a constraint they
no longer satisfy. Verified by hand: inserted an `approved` row, ran
`alembic downgrade -1`, confirmed Postgres rejects it with a check
violation, then cleaned up and re-verified the downgrade succeeds against
an empty table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e88d14230ad4"
down_revision: str | None = "28b3907984f5"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_OLD_STATUSES = ("generated",)
_NEW_STATUSES = ("generated", "pending_approval", "approved", "rejected")


def upgrade() -> None:
    op.add_column("content_drafts", sa.Column("rejection_reason", sa.Text(), nullable=True))
    op.add_column("content_drafts", sa.Column("approved_by", sa.Uuid(), nullable=True))
    op.add_column(
        "content_drafts", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_content_drafts_approved_by", "content_drafts", "users", ["approved_by"], ["id"]
    )
    op.drop_constraint("ck_content_drafts_status", "content_drafts", type_="check")
    op.create_check_constraint(
        "ck_content_drafts_status",
        "content_drafts",
        "status IN ('" + "','".join(_NEW_STATUSES) + "')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_content_drafts_status", "content_drafts", type_="check")
    op.create_check_constraint(
        "ck_content_drafts_status",
        "content_drafts",
        "status IN ('" + "','".join(_OLD_STATUSES) + "')",
    )
    op.drop_constraint("fk_content_drafts_approved_by", "content_drafts", type_="foreignkey")
    op.drop_column("content_drafts", "approved_at")
    op.drop_column("content_drafts", "approved_by")
    op.drop_column("content_drafts", "rejection_reason")
