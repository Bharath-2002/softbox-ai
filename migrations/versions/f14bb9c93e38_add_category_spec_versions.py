"""add category spec versions

Revision ID: f14bb9c93e38
Revises: dd47a2b7a9ac
Create Date: 2026-08-14 04:02:45.073837

D15's immutable publish record. ``UNIQUE (tenant_id, category_id, version)``
turns a concurrent double-publish into a loud constraint violation instead
of two rows racing to claim the same version number — allocating
``version`` via ``MAX(version) + 1`` is check-then-act (the same shape
CLAUDE.md §7 forbids for quota), so the constraint is the actual guard, not
the application-level allocation logic.

``status`` restates D15's schema literally (``draft|published|archived``)
even though this codebase never writes a ``draft`` row — see
``entities.category_spec_version`` for why. ``published_by`` is a plain FK
to ``users.id`` (not composite) because ``users`` itself is not
tenant-scoped, the same shape ``tenant_memberships.user_id`` already uses.

``snapshot`` has no default and is never nullable: a row only ever exists
because a publish just happened, so there is no "row exists, snapshot
pending" state to model (contrast ``idempotency_keys``, which legitimately
has one).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "f14bb9c93e38"
down_revision: str | None = "dd47a2b7a9ac"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_STATUSES = ("draft", "published", "archived")


def upgrade() -> None:
    op.create_table(
        "category_spec_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("change_summary", postgresql.JSONB(), nullable=True),
        sa.Column("published_by", sa.Uuid(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_category_spec_versions_category",
        ),
        sa.ForeignKeyConstraint(
            ["published_by"],
            ["users.id"],
            name="fk_category_spec_versions_published_by",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_category_spec_versions_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "category_id",
            "version",
            name="uq_category_spec_versions_tenant_category_version",
        ),
        sa.CheckConstraint(
            "status IN ('" + "','".join(_STATUSES) + "')",
            name="ck_category_spec_versions_status",
        ),
    )
    op.create_index("ix_category_spec_versions_tenant_id", "category_spec_versions", ["tenant_id"])
    op.create_index(
        "ix_category_spec_versions_tenant_category",
        "category_spec_versions",
        ["tenant_id", "category_id"],
    )

    enable_rls("category_spec_versions")
    create_tenant_isolation_policy("category_spec_versions")
    grant_to_app_role("category_spec_versions")


def downgrade() -> None:
    op.drop_table("category_spec_versions")
