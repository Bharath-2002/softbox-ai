"""widen assets.bytes to bigint

Revision ID: b2d4f0a3c8e6
Revises: a1c3e9f2b7d4
Create Date: 2026-08-14 08:00:00.000000

``integer`` caps at ~2.1 GB, comfortably above every cap this codebase
enforces today (``VerifyAndRegisterUpload`` defaults to 20 MB), but a byte
count is the conventional case for ``bigint`` and there is no reason to
carry the smaller type forward into a milestone that adds larger generated
renditions. A same-release follow-up to `a1c3e9f2b7d4` rather than an edit
to that migration - it already ran in CI and possibly in a local database,
and rewriting an applied migration in place is not how Alembic history
works. Pure type widening, no data loss, reversible.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d4f0a3c8e6"
down_revision: str | None = "a1c3e9f2b7d4"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("assets", "bytes", type_=sa.BigInteger(), existing_nullable=False)


def downgrade() -> None:
    op.alter_column("assets", "bytes", type_=sa.Integer(), existing_nullable=False)
