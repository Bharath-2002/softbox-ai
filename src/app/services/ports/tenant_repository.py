"""Platform-plane tenant reads (D4). ``tenants`` carries no RLS — it is the
root of the hierarchy, not a tenant-scoped table (see the bootstrap
migration's docstring) — so reading across every tenant is a legitimate
query, unlike any other port in this codebase.

Deliberately minimal: ``list_active`` is the one capability a cross-tenant
background process (the outbox relay, later a reconciler) needs — "which
tenants do I loop over". Full tenant CRUD (create, suspend, plan changes) is
M9's tenant-onboarding-flow territory, not built here; adding it later is
additive, not a breaking change to this port.
"""

from __future__ import annotations

from typing import Protocol

from app.shared.ids import TenantId


class TenantRepository(Protocol):
    async def list_active(self) -> list[TenantId]: ...
