"""add catalog templates

Revision ID: c4e6b1d9a72f
Revises: b2d4f0a3c8e6
Create Date: 2026-08-14 09:00:00.000000

D14's template record: an ``analysed_image`` (vision-analysed reference
photo) or an ``authored_scene`` (human-written prompt, no source photo) —
D0's resolution splitting templates into the two kinds a real fidelity
spike found necessary. Both run through the same state machine (see
``entities.catalog_template``'s module docstring).

``source_asset_id`` is a nullable composite FK to ``assets`` (both
tenant-scoped, so the composite guard applies) - null for ``authored_scene``.
``created_by`` is a plain FK to ``users.id`` (not composite), the same shape
``category_spec_versions.published_by``/``assets.uploaded_by`` already use.

``UNIQUE (tenant_id, catalog_image_slot_id, name, version)`` is the
versioning identity D14's "editing produces a new version" rule needs -
two versions of "the same template" share slot+name and differ by version.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "c4e6b1d9a72f"
down_revision: str | None = "b2d4f0a3c8e6"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_KINDS = ("analysed_image", "authored_scene")
_STATUSES = ("uploaded", "analysing", "analysed", "analysis_failed", "invalid", "archived")


def upgrade() -> None:
    op.create_table(
        "catalog_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("catalog_image_slot_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("source_asset_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("analysis", postgresql.JSONB(), nullable=True),
        sa.Column("prompt_template", sa.Text(), nullable=True),
        sa.Column("prompt_version", sa.Integer(), nullable=True),
        sa.Column("analysis_model", sa.Text(), nullable=True),
        sa.Column("analysed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analysis_error", sa.Text(), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "catalog_image_slot_id"],
            ["catalog_image_slots.tenant_id", "catalog_image_slots.id"],
            name="fk_catalog_templates_catalog_image_slot",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_asset_id"],
            ["assets.tenant_id", "assets.id"],
            name="fk_catalog_templates_source_asset",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["users.id"],
            name="fk_catalog_templates_created_by",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_catalog_templates_tenant_id_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "catalog_image_slot_id",
            "name",
            "version",
            name="uq_catalog_templates_slot_name_version",
        ),
        sa.CheckConstraint(
            "kind IN ('" + "','".join(_KINDS) + "')",
            name="ck_catalog_templates_kind",
        ),
        sa.CheckConstraint(
            "status IN ('" + "','".join(_STATUSES) + "')",
            name="ck_catalog_templates_status",
        ),
    )
    op.create_index("ix_catalog_templates_tenant_id", "catalog_templates", ["tenant_id"])
    op.create_index(
        "ix_catalog_templates_tenant_slot",
        "catalog_templates",
        ["tenant_id", "catalog_image_slot_id"],
    )

    enable_rls("catalog_templates")
    create_tenant_isolation_policy("catalog_templates")
    grant_to_app_role("catalog_templates")


def downgrade() -> None:
    op.drop_table("catalog_templates")
