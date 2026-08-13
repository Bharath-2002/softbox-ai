"""Unauthenticated storefront plane.

No router-level auth dependency — a shopper is not a signed-in principal.

CLAUDE.md §9 requires public routes to resolve their tenant from the Host
header (A1). That resolution is deliberately **not** built yet: it needs a
``tenant_domains`` table that does not exist (dropped from the identity
migration — see that migration's docstring), and there is no real public
route yet to prove the resolver against. Mounted now, empty, so the
``/api/v1`` URL surface is stable before the first storefront endpoint
lands; the Host-based tenant resolver and its no-cross-tenant-leakage test
land together with that first endpoint, not speculatively ahead of it.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/public", tags=["public"])
