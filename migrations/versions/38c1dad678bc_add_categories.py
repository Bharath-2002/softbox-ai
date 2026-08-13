"""add categories

Revision ID: 38c1dad678bc
Revises: 08dc87952293
Create Date: 2026-08-14 03:09:32.391455

The taxonomy's root table (D10). ``path`` is dot-separated ancestor ids as
plain ``text``, not Postgres's ``ltree`` — see ``entities/category.py``'s
module docstring for why (``ltree`` labels reject the hyphens in a UUID, and
this repo already dropped one extension-dependent column type, ``citext``,
for the identical "another cluster-bootstrap dependency" reason). Prefix
lookups (ancestors/descendants) use ``LIKE 'prefix.%'``, backed by the
``text_pattern_ops`` index below so the match stays index-only regardless of
the database's collation.

This is the first migration with a genuine composite foreign key (D2)
between two RLS-forced tables: ``categories (tenant_id, parent_id)`` ->
``categories (tenant_id, id)``, self-referential. A child row can only ever
point at a parent in its own tenant — Postgres enforces it, not application
code. No ``ON DELETE`` action is specified for that FK (defaults to
``RESTRICT``): nothing in this codebase hard-deletes a category (D15 keeps
spec rows forever, retired rather than dropped), so there is no intended
path that should cascade a delete through a subtree.

Key uniqueness is scoped to siblings, not the whole tenant — two different
subtrees may each define their own "size" axis without colliding. A plain
``UNIQUE (tenant_id, parent_id, key)`` cannot cover the root level, because
Postgres treats every NULL in a unique constraint as distinct from every
other NULL, which would let a tenant create the same root key twice. Two
partial unique indexes cover both cases instead.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role

revision: str = "38c1dad678bc"
down_revision: str | None = "08dc87952293"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "categories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("current_spec_version", sa.Integer(), nullable=True),
        sa.Column("draft_spec_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_categories_parent",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_categories_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "slug", name="uq_categories_tenant_id_slug"),
        sa.CheckConstraint("depth >= 0", name="ck_categories_depth_non_negative"),
    )
    op.create_index("ix_categories_tenant_id", "categories", ["tenant_id"])
    op.create_index("ix_categories_tenant_parent", "categories", ["tenant_id", "parent_id"])
    op.create_index(
        "ix_categories_tenant_path",
        "categories",
        ["tenant_id", "path"],
        postgresql_ops={"path": "text_pattern_ops"},
    )
    op.create_index(
        "uq_categories_root_key",
        "categories",
        ["tenant_id", "key"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NULL"),
    )
    op.create_index(
        "uq_categories_sibling_key",
        "categories",
        ["tenant_id", "parent_id", "key"],
        unique=True,
        postgresql_where=sa.text("parent_id IS NOT NULL"),
    )

    enable_rls("categories")
    create_tenant_isolation_policy("categories")
    grant_to_app_role("categories")


def downgrade() -> None:
    op.drop_table("categories")
