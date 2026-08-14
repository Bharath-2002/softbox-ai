"""add content_drafts

Revision ID: 28b3907984f5
Revises: c9e1a3f5b7d2
Create Date: 2026-08-15 09:00:00.000000

The current-state row per (variant, channel, locale) (D23) — copy is
subject to the same approval gate as imagery, so this table follows
`catalog_images`' exact shape: a mutable current-state row plus
`superseded_by` for full history, rather than editing a row in place.

That choice is load-bearing, not cosmetic: D21's `publications` table has a
`content_draft_id` FK. If a draft were mutable in place, editing the copy
of an already-published post would silently change what that FK resolves
to — the same problem `catalog_images.superseded_by` exists to prevent for
imagery. So editing a draft (not built yet — a later chunk) will mean
`mark_superseded` on the live row plus `create()` for the replacement, in
one transaction, the same two-write shape `CompleteGenerationItemRender`'s
regeneration path already uses for `catalog_images`.

Same constraint-interaction as `catalog_images`, reused verbatim: the
partial unique index (one **live** row per `(tenant_id, variant_id,
channel, locale)`, `WHERE superseded_by IS NULL`) is checked at the end of
each statement and forces `UPDATE` (retire) before `INSERT` (replace);
the self-referential `superseded_by` FK forces the opposite order on its
own, since the retiring row's `UPDATE` references a replacement that does
not exist yet at the time it runs. `fk_content_drafts_superseded_by` is
therefore `DEFERRABLE INITIALLY DEFERRED`, exactly like
`fk_catalog_images_superseded_by` — see that migration's docstring and
`tests/infrastructure/test_catalog_image_supersede.py` for the full
reasoning and the real-Postgres proof this repeats here in
`tests/infrastructure/test_content_draft_supersede.py`.

`channel` and `locale` are plain `Text`, not a domain enum with a `CHECK`
constraint — unlike `status`, these are closer to tenant/deployment
configuration than to fixed domain vocabulary (`docs/ARCHITECTURE.md`'s
D21 channel adapter list is expected to grow — `whatsapp_catalog`,
`google_merchant`, `shopify` are named as "later" — and constraining them
here would make adding one a migration for no correctness benefit).

`status` ships with a single valid value, `generated` — deliberately not
the full vocabulary a `catalog_image`-style state diagram would suggest
(`pending_approval`/`approved`/`rejected`/...). Unlike D18's `catalog_image`
diagram, D23 gives no authoritative state diagram for `content_drafts` to
build against, and guessing the full set now risks the same
speculative-generic mistake the `workflow_runs` deferral avoided earlier
this project — the approval-gate chunk that actually drives those
transitions will extend this `CHECK` constraint via a normal expand
migration when it lands.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from migrations.rls import create_tenant_isolation_policy, enable_rls, grant_to_app_role
from sqlalchemy.dialects import postgresql

revision: str = "28b3907984f5"
down_revision: str | None = "c9e1a3f5b7d2"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

_STATUSES = ("generated",)


def upgrade() -> None:
    op.create_table(
        "content_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("variant_id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("locale", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("hashtags", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("cta", sa.Text(), nullable=True),
        sa.Column("alt_text", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("edited_by", sa.Uuid(), nullable=True),
        sa.Column("superseded_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_content_drafts_variant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "superseded_by"],
            ["content_drafts.tenant_id", "content_drafts.id"],
            name="fk_content_drafts_superseded_by",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["edited_by"],
            ["users.id"],
            name="fk_content_drafts_edited_by",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_content_drafts_tenant_id_id"),
        sa.CheckConstraint(
            "status IN ('" + "','".join(_STATUSES) + "')",
            name="ck_content_drafts_status",
        ),
    )
    op.create_index("ix_content_drafts_tenant_id", "content_drafts", ["tenant_id"])
    op.create_index(
        "ix_content_drafts_live_per_variant_channel_locale",
        "content_drafts",
        ["tenant_id", "variant_id", "channel", "locale"],
        unique=True,
        postgresql_where=sa.text("superseded_by IS NULL"),
    )

    enable_rls("content_drafts")
    create_tenant_isolation_policy("content_drafts")
    grant_to_app_role("content_drafts")


def downgrade() -> None:
    op.drop_table("content_drafts")
