"""HTTP-level tests for ``/api/v1/admin/categories/*`` — the first M2 entity
reachable over HTTP. Only the low-level port providers
(``get_uow_factory``, ``get_clock``, ``get_token_issuer``) are overridden;
every ``bootstrap/di.py`` use-case provider runs for real, so this proves
the actual wiring (router -> DI -> use case -> fake UnitOfWork), same
approach as ``test_auth_router.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import get_token_issuer
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.category import Category
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_category_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _build() -> tuple[object, FakeUnitOfWorkFactory, FakeClock, AccessTokenCodec]:
    settings = Settings(
        environment="test", log_format="console", access_token_signing_key=SIGNING_KEY
    )
    app = create_app(settings)
    uow_factory = FakeUnitOfWorkFactory()
    clock = FakeClock(_NOW)
    codec = AccessTokenCodec(SIGNING_KEY)

    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_token_issuer] = lambda: codec
    return app, uow_factory, clock, codec


def _bearer(
    codec: AccessTokenCodec,
    *,
    tenant_id: str | None,
    role: str | None,
    capabilities: list[str],
    is_platform_admin: bool = False,
) -> dict[str, str]:
    # Encoded against the real wall clock, not the fixed `_NOW` the fake
    # domain clock uses - `get_current_principal` decodes with
    # `now=utcnow()` (the actual request time), so a token stamped with a
    # historical `_NOW` reads as already expired.
    token = codec.encode(
        AccessTokenClaims(
            subject=str(new_user_id()),
            tenant_id=tenant_id,
            role=role,
            capabilities=capabilities,
            is_platform_admin=is_platform_admin,
        ),
        now=utcnow(),
    )
    return {"Authorization": f"Bearer {token}"}


async def _client(app: object) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_creating_a_category_requires_the_taxonomy_capability() -> None:
    app, _uow, _clock, codec = _build()
    headers = _bearer(codec, tenant_id=str(new_tenant_id()), role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/admin/categories",
            json={"key": "apparel", "name": "Apparel", "slug": "apparel"},
            headers=headers,
        )

    assert response.status_code == 403


async def test_creating_and_fetching_a_category_round_trips() -> None:
    app, _uow, _clock, codec = _build()
    tenant_id = str(new_tenant_id())
    headers = _bearer(
        codec,
        tenant_id=tenant_id,
        role="admin",
        capabilities=["taxonomy.manage", "catalog.publish"],
    )

    async with await _client(app) as http:
        create_response = await http.post(
            "/api/v1/admin/categories",
            json={"key": "apparel", "name": "Apparel", "slug": "apparel"},
            headers=headers,
        )
        assert create_response.status_code == 201
        category_id = create_response.json()["id"]

        get_response = await http.get(f"/api/v1/admin/categories/{category_id}", headers=headers)

    assert get_response.status_code == 200
    body = get_response.json()
    assert body["name"] == "Apparel"
    assert body["parent_id"] is None
    assert body["depth"] == 0


async def test_a_viewer_can_read_but_not_write() -> None:
    app, uow_factory, clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    await uow_factory.categories.add(category)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        get_response = await http.get(f"/api/v1/admin/categories/{category.id}", headers=headers)
        update_response = await http.patch(
            f"/api/v1/admin/categories/{category.id}",
            json={"name": "Renamed"},
            headers=headers,
        )

    assert get_response.status_code == 200
    assert update_response.status_code == 403


async def test_updating_a_category_changes_its_editable_fields() -> None:
    app, uow_factory, clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    await uow_factory.categories.add(category)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["taxonomy.manage"]
    )

    async with await _client(app) as http:
        response = await http.patch(
            f"/api/v1/admin/categories/{category.id}",
            json={"name": "Renamed", "description": "d", "position": 2, "is_active": False},
            headers=headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Renamed"
    assert body["is_active"] is False


async def test_listing_root_categories() -> None:
    app, uow_factory, clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    root = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    await uow_factory.categories.add(root)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.get("/api/v1/admin/categories", headers=headers)

    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == [str(root.id)]


async def test_moving_a_category() -> None:
    app, uow_factory, clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    root = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    other_root = Category.create(
        tenant_id, key="home", name="Home", slug="home", parent=None, now=clock.now()
    )
    await uow_factory.categories.add(root)
    await uow_factory.categories.add(other_root)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["taxonomy.manage"]
    )

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/categories/{root.id}/move",
            json={"new_parent_id": str(other_root.id)},
            headers=headers,
        )

    assert response.status_code == 204
    moved = await uow_factory.categories.get(tenant_id, root.id)
    assert moved is not None
    assert moved.parent_id == other_root.id


async def test_publishing_a_category_spec() -> None:
    app, uow_factory, clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    await uow_factory.categories.add(category)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["catalog.publish"]
    )

    async with await _client(app) as http:
        publish_response = await http.post(
            f"/api/v1/admin/categories/{category.id}/publish", headers=headers
        )
        assert publish_response.status_code == 200
        version = publish_response.json()["version"]

        spec_response = await http.get(
            f"/api/v1/admin/categories/{category.id}/spec-versions/{version}", headers=headers
        )

    assert spec_response.status_code == 200
    assert "attribute_definitions" in spec_response.json()


async def test_publishing_without_the_catalog_publish_capability_is_rejected() -> None:
    app, uow_factory, clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=clock.now()
    )
    await uow_factory.categories.add(category)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["taxonomy.manage"]
    )

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/categories/{category.id}/publish", headers=headers
        )

    assert response.status_code == 403


async def test_reading_an_unpublished_spec_version_is_not_found() -> None:
    app, _uow, _clock, codec = _build()
    headers = _bearer(codec, tenant_id=str(new_tenant_id()), role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.get(
            f"/api/v1/admin/categories/{new_category_id()}/spec-versions/1", headers=headers
        )

    assert response.status_code == 404


async def test_a_platform_only_token_is_rejected_by_the_admin_plane() -> None:
    app, _uow, _clock, codec = _build()
    headers = _bearer(codec, tenant_id=None, role=None, capabilities=[], is_platform_admin=True)

    async with await _client(app) as http:
        response = await http.get("/api/v1/admin/categories", headers=headers)

    assert response.status_code == 403
