"""add attribute definitions

Revision ID: 18c4ff8a7a48
Revises: 38c1dad678bc
Create Date: 2026-08-14 04:02:11.000000

The definition half of D11's custom-fields design. The other two parts -
``products.attributes`` JSONB storage and the runtime Pydantic compilation
that validates against it - land with M4 (a ``products`` table to store
values in) and the very next chunk (compilation is pure, needs no table)
respectively. This migration only records what a field *is*: its type,
constraints and whether it means something structurally to the platform
(``semantic_role``).

``(tenant_id, category_id)`` -> ``categories (tenant_id, id)`` is this
schema's second composite foreign key between two RLS-forced tables (D2),
and the first one that isn't self-referential - ``categories``' own
parent-pointer proved the mechanism works in the previous migration; this
proves it generalises to an ordinary child-table reference.

No uniqueness constraint on ``(tenant_id, category_id, key)``: a category
and one of its ancestors are permitted to define the same key deliberately
(D15's "additive" changes and, later, spec versioning both need a
category to redefine or override an inherited key without the schema
getting in the way) - resolution order, not a uniqueness rule, is what makes
one of them win (``services/spec_inheritance.py``, next chunk).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "18c4ff8a7a48"
down_revision: str | None = "38c1dad678bc"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_DATA_TYPES = (
    "text",
    "long_text",
    "integer",
    "decimal",
    "money",
    "boolean",
    "date",
    "enum",
    "multi_enum",
    "url",
    "image_ref",
    "dimension",
)
_SEMANTIC_ROLES = ("title", "description", "price", "sku", "brand", "material", "colour")


def upgrade() -> None:
    op.create_table(
        "attribute_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("help_text", sa.Text(), nullable=True),
        sa.Column("data_type", sa.Text(), nullable=False),
        sa.Column("semantic_role", sa.Text(), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("is_filterable", sa.Boolean(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("validation", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("ui", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("default_value", postgresql.JSONB(), nullable=True),
        sa.Column("introduced_in_version", sa.Integer(), nullable=True),
        sa.Column("retired_in_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_attribute_definitions_category",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_attribute_definitions_tenant_id_id"),
        sa.CheckConstraint(
            "data_type IN ('" + "','".join(_DATA_TYPES) + "')",
            name="ck_attribute_definitions_data_type",
        ),
        sa.CheckConstraint(
            "semantic_role IS NULL OR semantic_role IN ('" + "','".join(_SEMANTIC_ROLES) + "')",
            name="ck_attribute_definitions_semantic_role",
        ),
    )
    op.create_index("ix_attribute_definitions_tenant_id", "attribute_definitions", ["tenant_id"])
    op.create_index(
        "ix_attribute_definitions_tenant_category",
        "attribute_definitions",
        ["tenant_id", "category_id"],
    )

    enable_rls("attribute_definitions")
    create_tenant_isolation_policy("attribute_definitions")
    grant_to_app_role("attribute_definitions")


def downgrade() -> None:
    op.drop_table("attribute_definitions")
