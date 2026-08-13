"""add settings

Revision ID: 77ef8de529f6
Revises: f14bb9c93e38
Create Date: 2026-08-14 08:12:00.000000

Hierarchical configuration (D16): one table for platform defaults, tenant
overrides, and category/product overrides, resolved most-specific-wins by
``services.settings_resolver.SettingsResolver``.

``tenant_id`` is nullable — a platform-level row (``scope_type='platform'``)
belongs to no tenant, and must stay visible to every tenant's resolution
chain as the fallback default. That breaks the usual single-line
``create_tenant_isolation_policy`` predicate two ways at once, so this
migration writes its own policy instead of calling that helper:

- **Read**: a row is visible if it has no tenant (platform-wide) *or* its
  tenant matches the bound one — never another tenant's row.
- **Write**: a row may only be written if its own ``tenant_id`` matches the
  bound tenant, *or* the row is platform-wide (``tenant_id IS NULL``) and no
  tenant is bound at all (a platform-plane session, ``tenant_id=None`` in
  ``UnitOfWorkFactory`` terms). A tenant-bound session can never write a
  platform-wide row, and a platform-plane session can never write a
  tenant's row.

Postgres treats every ``NULL`` in a plain ``UNIQUE`` constraint as distinct
from every other row (the same trap ``categories``' sibling-key uniqueness
hit) — ``scope_id`` is ``NULL`` for both platform and tenant scope, so a
single composite ``UNIQUE`` would never actually catch a tenant setting the
same key twice at the tenant level. Three partial unique indexes, one per
"shape" of row, the same fix ``categories`` used.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "77ef8de529f6"
down_revision: str | None = "f14bb9c93e38"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_SCOPE_TYPES = ("platform", "tenant", "category", "product")


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("scope_type", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Uuid(), nullable=True),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "scope_type IN ('" + "','".join(_SCOPE_TYPES) + "')",
            name="ck_settings_scope_type",
        ),
        sa.CheckConstraint(
            "(scope_type = 'platform' AND tenant_id IS NULL AND scope_id IS NULL) OR "
            "(scope_type = 'tenant' AND tenant_id IS NOT NULL AND scope_id IS NULL) OR "
            "(scope_type IN ('category', 'product') AND tenant_id IS NOT NULL "
            "AND scope_id IS NOT NULL)",
            name="ck_settings_scope_consistency",
        ),
    )
    op.create_index(
        "uq_settings_platform_key",
        "settings",
        ["key"],
        unique=True,
        postgresql_where=sa.text("scope_type = 'platform'"),
    )
    op.create_index(
        "uq_settings_tenant_key",
        "settings",
        ["tenant_id", "key"],
        unique=True,
        postgresql_where=sa.text("scope_type = 'tenant'"),
    )
    op.create_index(
        "uq_settings_scoped_key",
        "settings",
        ["tenant_id", "scope_type", "scope_id", "key"],
        unique=True,
        postgresql_where=sa.text("scope_id IS NOT NULL"),
    )
    op.create_index("ix_settings_tenant_id", "settings", ["tenant_id"])

    op.execute("ALTER TABLE settings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE settings FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY settings_tenant_isolation ON settings "
        "USING ("
        "  tenant_id IS NULL"
        "  OR tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
        ") "
        "WITH CHECK ("
        "  tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
        "  OR (tenant_id IS NULL "
        "      AND NULLIF(current_setting('app.current_tenant', true), '') IS NULL)"
        ")"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON settings TO softbox_app")


def downgrade() -> None:
    op.drop_table("settings")
