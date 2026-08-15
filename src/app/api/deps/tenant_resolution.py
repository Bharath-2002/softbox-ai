"""Tenant resolution for the ``public`` router (D4, CLAUDE.md §9): a
storefront request carries no session, so its tenant comes from the Host
header instead of a bearer token — the ``public`` counterpart to
``get_current_principal``.

``NotFoundError`` for an unresolvable hostname, not a more specific "unknown
domain" error: the same "do not distinguish missing from someone else's"
reasoning ``NotFoundError`` itself documents, applied one level up — telling
an unrecognised caller that domain resolution specifically is what failed is
still more than they need to know.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.bootstrap.di import ResolveTenantFromHostDep
from app.shared.errors import NotFoundError
from app.shared.ids import TenantId


def _hostname(request: Request) -> str:
    host = request.headers.get("host", "")
    return host.split(":", 1)[0].strip().lower()


async def get_public_tenant_id(request: Request, resolve: ResolveTenantFromHostDep) -> TenantId:
    tenant_id = await resolve(hostname=_hostname(request))
    if tenant_id is None:
        raise NotFoundError("No storefront is registered for this domain.")
    return tenant_id


PublicTenantIdDep = Annotated[TenantId, Depends(get_public_tenant_id)]
