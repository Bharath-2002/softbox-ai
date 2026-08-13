"""``require_capability`` tested end-to-end with a fabricated ``Principal`` —
no HTTP round-trip, no token validation, per the commit-2 scope: this
dependency's own logic does not change once real authentication exists.
"""

from __future__ import annotations

import pytest

from app.api.deps.authorization import get_current_principal, require_capability
from app.entities.capabilities import Capability
from app.entities.principal import Principal
from app.entities.roles import Role
from app.shared.errors import PermissionDeniedError
from app.shared.ids import new_tenant_id, new_user_id


async def test_get_current_principal_fails_loudly_not_silently() -> None:
    """No route may depend on this before OIDC lands (commit 3) - it must
    error, never fabricate a principal."""
    with pytest.raises(NotImplementedError):
        await get_current_principal()


async def test_require_capability_allows_a_principal_that_has_it() -> None:
    principal = Principal(
        user_id=new_user_id(),
        tenant_id=new_tenant_id(),
        role=Role.CATALOG_MANAGER,
        capabilities=frozenset({Capability.CATALOG_PUBLISH}),
    )
    dependency = require_capability(Capability.CATALOG_PUBLISH)

    result = await dependency(principal)

    assert result is principal


async def test_require_capability_denies_a_principal_missing_it() -> None:
    principal = Principal(
        user_id=new_user_id(),
        tenant_id=new_tenant_id(),
        role=Role.VIEWER,
        capabilities=frozenset(),
    )
    dependency = require_capability(Capability.CATALOG_PUBLISH)

    with pytest.raises(PermissionDeniedError):
        await dependency(principal)
