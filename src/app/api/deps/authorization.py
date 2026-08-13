"""Capability enforcement at the route boundary (D4).

``require_capability`` is the reusable part and does not change once real
authentication exists — it only needs a ``Principal``, however one was
obtained. ``get_current_principal`` is the one piece that does change: today
it fails loudly rather than authenticating anyone, because token validation
does not exist yet (M1 chunk 4 commit 3, OIDC). This is an explicit,
documented placeholder for a specifically planned follow-up, not a stub that
pretends to work - no route may depend on it before commit 3 replaces it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends

from app.entities.capabilities import Capability
from app.entities.principal import Principal


async def get_current_principal() -> Principal:
    raise NotImplementedError(
        "Token-based authentication is not wired yet (M1 chunk 4 commit 3 - OIDC). "
        "No route may depend on get_current_principal before then."
    )


PrincipalDep = Annotated[Principal, Depends(get_current_principal)]


def require_capability(capability: Capability | str) -> Callable[[Principal], Awaitable[Principal]]:
    """A route dependency: ``Depends(require_capability(Capability.CATALOG_PUBLISH))``.

    Returns the principal so a route can use it further (audit logging the
    actor, for instance) without a second lookup.
    """

    async def dependency(principal: PrincipalDep) -> Principal:
        principal.require_capability(capability)
        return principal

    return dependency
