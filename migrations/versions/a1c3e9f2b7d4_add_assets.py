"""add assets

Revision ID: a1c3e9f2b7d4
Revises: 77ef8de529f6
Create Date: 2026-08-14 07:00:00.000000

D17's content-addressed asset record. A row is only ever written after a
presigned direct upload has been verified (size, sniffed MIME, dimensions,
abuse/NSFW scan) - see ``entities.asset`` for why there is no "pending"
status to model here, the same reasoning ``category_spec_versions`` used for
never writing a ``draft`` row.

``UNIQUE (tenant_id, sha256, kind)`` is the dedup guard - the same bytes
reused for the same ``kind`` collapses to one row. ``parent_asset_id`` is a
self-referencing composite FK (``(tenant_id, parent_asset_id) ->
assets (tenant_id, id)``), nullable and unused until the per-channel
derivative renditions in a later milestone - included now so that table
does not need a later ALTER. ``uploaded_by`` is a plain FK to ``users.id``
(not composite, same shape ``category_spec_versions.published_by`` uses)
and nullable, since a ``generated`` or ``derivative`` asset has no human
uploader.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "a1c3e9f2b7d4"
down_revision: str | None = "77ef8de529f6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_KINDS = ("template", "input", "generated", "derivative")


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("mime", sa.Text(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("parent_asset_id", sa.Uuid(), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("uploaded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "parent_asset_id"],
            ["assets.tenant_id", "assets.id"],
            name="fk_assets_parent_asset",
        ),
        sa.ForeignKeyConstraint(
            ["uploaded_by"],
            ["users.id"],
            name="fk_assets_uploaded_by",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_assets_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "sha256", "kind", name="uq_assets_tenant_sha256_kind"),
        sa.CheckConstraint(
            "kind IN ('" + "','".join(_KINDS) + "')",
            name="ck_assets_kind",
        ),
    )
    op.create_index("ix_assets_tenant_id", "assets", ["tenant_id"])

    enable_rls("assets")
    create_tenant_isolation_policy("assets")
    grant_to_app_role("assets")


def downgrade() -> None:
    op.drop_table("assets")
