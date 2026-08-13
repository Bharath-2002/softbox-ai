"""The four planes (CLAUDE.md §9) are mounted under the API prefix with the
right auth posture attached at router level.

``admin`` carries real routes now (``admin_taxonomy.py``); ``platform``,
``public`` and ``webhooks`` do not yet, so every router still gets a
throwaway probe route appended to the real router objects for the duration
of one test and removed afterward — the same approach ``test_api_basics.py``
uses for the ops routes, extended here to also prove that ``create_app()``
actually wires router-level ``dependencies=[...]`` end to end, not just that
the dependency functions are individually correct (see
``test_authorization_deps.py`` for that unit-level coverage, and
``test_admin_taxonomy_router.py`` for the real admin routes).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import require_platform_admin, require_tenant_context
from app.api.routers import admin, platform, public, webhooks
from app.bootstrap.app import create_app
from app.bootstrap.settings import Settings
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.ids import new_tenant_id, new_user_id

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"
TEST_SETTINGS = Settings(
    environment="test", log_format="console", access_token_signing_key=SIGNING_KEY
)


async def _probe() -> dict[str, bool]:
    return {"ok": True}


@pytest.fixture
def probed_app() -> AsyncIterator[object]:
    """Adds ``GET .../__probe__`` to each of the four routers, builds the
    app (which reads each router's ``.routes`` at ``include_router`` time),
    then removes the probe route so no other test observes it."""
    routers = (admin.router, platform.router, public.router, webhooks.router)
    for router in routers:
        router.add_api_route("/__probe__", _probe, methods=["GET"])
    app = create_app(TEST_SETTINGS)
    try:
        yield app
    finally:
        for router in routers:
            router.routes.pop()


def _bearer_header(**claims: object) -> dict[str, str]:
    codec = AccessTokenCodec(SIGNING_KEY)
    token = codec.encode(AccessTokenClaims(**claims), now=utcnow())  # type: ignore[arg-type]
    return {"Authorization": f"Bearer {token}"}


async def _get(app: object, path: str, headers: dict[str, str] | None = None):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        return await http.get(f"{TEST_SETTINGS.api_prefix}{path}", headers=headers or {})


async def test_admin_route_requires_a_bearer_token(probed_app: object) -> None:
    response = await _get(probed_app, "/admin/__probe__")
    assert response.status_code == 401


async def test_admin_route_rejects_a_platform_only_token(probed_app: object) -> None:
    headers = _bearer_header(
        subject=str(new_user_id()),
        tenant_id=None,
        role=None,
        capabilities=[],
        is_platform_admin=True,
    )
    response = await _get(probed_app, "/admin/__probe__", headers)
    assert response.status_code == 403


async def test_admin_route_allows_a_tenant_bound_token(probed_app: object) -> None:
    headers = _bearer_header(
        subject=str(new_user_id()),
        tenant_id=str(new_tenant_id()),
        role="viewer",
        capabilities=[],
        is_platform_admin=False,
    )
    response = await _get(probed_app, "/admin/__probe__", headers)
    assert response.status_code == 200


async def test_platform_route_rejects_a_tenant_bound_token(probed_app: object) -> None:
    headers = _bearer_header(
        subject=str(new_user_id()),
        tenant_id=str(new_tenant_id()),
        role="owner",
        capabilities=[],
        is_platform_admin=False,
    )
    response = await _get(probed_app, "/platform/__probe__", headers)
    assert response.status_code == 403


async def test_platform_route_allows_a_platform_admin_token(probed_app: object) -> None:
    headers = _bearer_header(
        subject=str(new_user_id()),
        tenant_id=None,
        role=None,
        capabilities=[],
        is_platform_admin=True,
    )
    response = await _get(probed_app, "/platform/__probe__", headers)
    assert response.status_code == 200


async def test_public_route_needs_no_credentials(probed_app: object) -> None:
    response = await _get(probed_app, "/public/__probe__")
    assert response.status_code == 200


async def test_webhooks_route_needs_no_credentials(probed_app: object) -> None:
    response = await _get(probed_app, "/webhooks/__probe__")
    assert response.status_code == 200


def test_admin_router_carries_the_tenant_context_dependency() -> None:
    dependencies = [d.dependency for d in admin.router.dependencies]
    assert require_tenant_context in dependencies


def test_platform_router_carries_the_platform_admin_dependency() -> None:
    dependencies = [d.dependency for d in platform.router.dependencies]
    assert require_platform_admin in dependencies


def test_public_and_webhooks_routers_carry_no_router_level_auth_dependency() -> None:
    assert public.router.dependencies == []
    assert webhooks.router.dependencies == []
