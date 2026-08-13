"""The immutable published-spec snapshot (D15) — the piece that prevents
slow decay. Once a version's ``snapshot`` is written, that JSONB blob is
what every consumer reads back verbatim: generation, a regeneration two
years later, an old product's pinned spec.

D15's schema lists ``status (draft|published|archived)``, but this codebase
never constructs a ``draft`` row here. "Nothing reads the live slot tables
except the spec editor" only holds if a draft is *not* a second, mutable
representation living in this table — the editor's live view already is
the definition tables themselves (D10-D13), filtered by ``category_id``,
unfiltered by ``introduced_in_version``. ``categories.draft_spec_version``
already tracks "the next version number to allocate" as a plain integer,
with no row here needed to back it. ``SpecVersionStatus.DRAFT`` is kept only
because the migration's ``CHECK`` constraint restates D15's schema
literally; ``CategorySpecVersion.create`` refuses to build one.

``ARCHIVED`` is a real future status (a category or its whole spec being
retired) with no writer yet — nothing in M2 needs it, and CLAUDE.md says not
to build a transition with nothing to call it.

Immutability itself is enforced one layer up, at the port
(``services.ports.category_spec_version_repository``): the repository has no
``update`` method, so no code path in this codebase can express mutating a
published snapshot. See that port's docstring, and
``services.attribute_model_compiler.AttributeModelCache``, whose caching
correctness depends on this property.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.shared.ids import (
    CategoryId,
    CategorySpecVersionId,
    TenantId,
    UserId,
    new_category_spec_version_id,
)


class SpecVersionStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


@dataclass
class CategorySpecVersion:
    id: CategorySpecVersionId
    tenant_id: TenantId
    category_id: CategoryId
    version: int
    status: SpecVersionStatus
    snapshot: dict[str, Any]
    change_summary: dict[str, Any] | None
    published_by: UserId
    published_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        category_id: CategoryId,
        *,
        version: int,
        snapshot: dict[str, Any],
        published_by: UserId,
        now: datetime,
        change_summary: dict[str, Any] | None = None,
    ) -> CategorySpecVersion:
        return CategorySpecVersion(
            id=new_category_spec_version_id(),
            tenant_id=tenant_id,
            category_id=category_id,
            version=version,
            status=SpecVersionStatus.PUBLISHED,
            snapshot=snapshot,
            change_summary=change_summary,
            published_by=published_by,
            published_at=now,
        )
