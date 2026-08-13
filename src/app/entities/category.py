"""A tenant's own product taxonomy (D10).

``path`` is a materialised path stored as dot-separated ancestor ids
(``root_id.child_id.grandchild_id``, self included at the tail) — plain
``text``, not Postgres's ``ltree`` extension. ``ltree`` labels only permit
alphanumerics and underscores, which a UUID's hyphens violate outright, and
this codebase already rejected an extension-dependent column type once
before for the same reason (``citext``, chunk 3's identity migration): one
more thing every environment must have installed, for a feature a plain
column gets without it. Ancestor and descendant queries use ``LIKE`` prefix
matching on this column instead of ``ltree`` operators.

``path``/``depth`` are derived, not authoritative — recomputing them for a
whole subtree on reparent is ``app.services.category_hierarchy``'s job, not
this entity's. A ``Category`` only knows how to place itself under a given
parent at creation time.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.shared.ids import CategoryId, TenantId, new_category_id


@dataclass
class Category:
    id: CategoryId
    tenant_id: TenantId
    parent_id: CategoryId | None
    path: str
    depth: int
    key: str
    name: str
    slug: str
    description: str | None
    position: int
    is_active: bool
    current_spec_version: int | None
    draft_spec_version: int | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        *,
        key: str,
        name: str,
        slug: str,
        parent: Category | None,
        now: datetime,
        description: str | None = None,
        position: int = 0,
    ) -> Category:
        category_id = new_category_id()
        if parent is None:
            path = str(category_id)
            depth = 0
        else:
            path = f"{parent.path}.{category_id}"
            depth = parent.depth + 1
        return Category(
            id=category_id,
            tenant_id=tenant_id,
            parent_id=parent.id if parent is not None else None,
            path=path,
            depth=depth,
            key=key,
            name=name,
            slug=slug,
            description=description,
            position=position,
            is_active=True,
            current_spec_version=None,
            draft_spec_version=None,
            created_at=now,
            updated_at=now,
        )

    def ancestor_ids(self) -> list[CategoryId]:
        """Root-to-leaf, self included — parsed from ``path`` rather than a
        database round trip per ancestor. This is what
        ``app.services.spec_inheritance.resolve_inherited`` walks."""
        return [CategoryId(uuid.UUID(part)) for part in self.path.split(".")]
