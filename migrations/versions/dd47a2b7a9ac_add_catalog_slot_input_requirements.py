"""add catalog slot input requirements

Revision ID: dd47a2b7a9ac
Revises: f456e393914a
Create Date: 2026-08-14 06:45:00.000000

The sharing join (D13) - what actually makes one photograph feed several
catalog images. No synthetic id: the composite primary key is the pair
itself, (``catalog_image_slot_id``, ``input_image_slot_id``) - a catalog
slot either requires a given input or it does not.

Two composite foreign keys (D2), both into tables this migration's
predecessors already gave a ``UNIQUE (tenant_id, id)`` to:
``(tenant_id, catalog_image_slot_id) -> catalog_image_slots (tenant_id,
id)`` and ``(tenant_id, input_image_slot_id) -> input_image_slots (tenant_id,
id)``. A row can only pair a catalog slot and an input slot that belong to
the *same* tenant - Postgres enforces it twice over, once per side.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role

revision: str = "dd47a2b7a9ac"
down_revision: str | None = "f456e393914a"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "catalog_slot_input_requirements",
        sa.Column("catalog_image_slot_id", sa.Uuid(), primary_key=True),
        sa.Column("input_image_slot_id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("prompt_position", sa.Integer(), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "catalog_image_slot_id"],
            ["catalog_image_slots.tenant_id", "catalog_image_slots.id"],
            name="fk_catalog_slot_input_requirements_catalog_slot",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "input_image_slot_id"],
            ["input_image_slots.tenant_id", "input_image_slots.id"],
            name="fk_catalog_slot_input_requirements_input_slot",
        ),
    )
    op.create_index(
        "ix_catalog_slot_input_requirements_tenant_id",
        "catalog_slot_input_requirements",
        ["tenant_id"],
    )
    op.create_index(
        "ix_catalog_slot_input_requirements_input_slot",
        "catalog_slot_input_requirements",
        ["tenant_id", "input_image_slot_id"],
    )

    enable_rls("catalog_slot_input_requirements")
    create_tenant_isolation_policy("catalog_slot_input_requirements")
    grant_to_app_role("catalog_slot_input_requirements")


def downgrade() -> None:
    op.drop_table("catalog_slot_input_requirements")
