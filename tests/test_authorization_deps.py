"""``require_capability`` and ``get_current_principal`` (D4).

``require_capability`` is tested with a fabricated ``Principal`` — no HTTP
round-trip needed, since its logic never touches the request. As of M1 chunk
4 commit 3, ``get_current_principal`` does real work (decoding a bearer
token via ``TokenIssuer``) and is tested against a real ``AccessTokenCodec``
directly, bypassing FastAPI's dependency injection machinery — the function
itself is what is under test, not the framework wiring around it.

Tokens here are encoded against ``utcnow()`` (real wall-clock time), not a
fixed fake timestamp — ``get_current_principal`` checks expiry against real
time internally rather than accepting an injectable ``Clock``, deliberately:
a fake clock at the authentication boundary would be a way to keep a token
alive past its real expiry, which is exactly the property a short-lived
access token exists to prevent. Confirmed by first writing this against a
fixed 2026-01-01 timestamp, which failed because it had already "expired"
relative to whenever the suite actually runs — the correct fix was the test,
not the production code.
"""

from __future__ import annotations

import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps.authorization import get_current_principal, require_capability
from app.entities.capabilities import Capability
from app.entities.principal import Principal
from app.entities.roles import Role
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.errors import AuthenticationError, PermissionDeniedError
from app.shared.ids import new_tenant_id, new_user_id

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_missing_credentials_are_rejected() -> None:
    codec = AccessTokenCodec(SIGNING_KEY)

    with pytest.raises(AuthenticationError, match="Missing bearer token"):
        await get_current_principal(None, codec)


async def test_a_valid_access_token_resolves_the_matching_principal() -> None:
    codec = AccessTokenCodec(SIGNING_KEY)
    user_id = new_user_id()
    tenant_id = new_tenant_id()
    token = codec.encode(
        AccessTokenClaims(
            subject=str(user_id),
            tenant_id=str(tenant_id),
            role="admin",
            capabilities=["catalog.publish", "member.manage"],
            is_platform_admin=False,
        ),
        now=utcnow(),
    )

    principal = await get_current_principal(_bearer(token), codec)

    assert principal.user_id == user_id
    assert principal.tenant_id == tenant_id
    assert principal.role == Role.ADMIN
    assert principal.has_capability(Capability.CATALOG_PUBLISH)
    assert principal.has_capability(Capability.MEMBER_MANAGE)
    assert principal.is_platform_admin is False


async def test_a_platform_scoped_token_resolves_with_no_tenant_or_role() -> None:
    codec = AccessTokenCodec(SIGNING_KEY)
    user_id = new_user_id()
    token = codec.encode(
        AccessTokenClaims(
            subject=str(user_id),
            tenant_id=None,
            role=None,
            capabilities=[],
            is_platform_admin=True,
        ),
        now=utcnow(),
    )

    principal = await get_current_principal(_bearer(token), codec)

    assert principal.tenant_id is None
    assert principal.role is None
    assert principal.is_platform_admin is True


async def test_an_invalid_token_is_rejected() -> None:
    codec = AccessTokenCodec(SIGNING_KEY)

    with pytest.raises(AuthenticationError):
        await get_current_principal(_bearer("not-a-real-token"), codec)


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
