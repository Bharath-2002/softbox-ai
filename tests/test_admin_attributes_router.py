"""HTTP-level tests for ``/api/v1/admin/{categories,attribute-definitions,
variant-axes,variant-axis-values}/*`` — chunk B of the M2 Admin API. Same
build/bearer-token approach as ``test_admin_taxonomy_router.py``.
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
from app.shared.ids import TenantId, new_tenant_id, new_user_id
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
    codec: AccessTokenCodec, *, tenant_id: str, role: str, capabilities: list[str]
) -> dict[str, str]:
    token = codec.encode(
        AccessTokenClaims(
            subject=str(new_user_id()),
            tenant_id=tenant_id,
            role=role,
            capabilities=capabilities,
            is_platform_admin=False,
        ),
        now=utcnow(),
    )
    return {"Authorization": f"Bearer {token}"}


async def _client(app: object) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _seed_category(uow_factory: FakeUnitOfWorkFactory, tenant_id: TenantId) -> Category:
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)
    return category


async def test_creating_and_listing_an_attribute_definition() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category = await _seed_category(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["taxonomy.manage"]
    )

    async with await _client(app) as http:
        create_response = await http.post(
            f"/api/v1/admin/categories/{category.id}/attribute-definitions",
            json={"key": "fabric", "label": "Fabric", "data_type": "text"},
            headers=headers,
        )
        assert create_response.status_code == 201

        list_response = await http.get(
            f"/api/v1/admin/categories/{category.id}/attribute-definitions", headers=headers
        )

    assert list_response.status_code == 200
    [definition] = list_response.json()
    assert definition["key"] == "fabric"


async def test_creating_an_attribute_definition_requires_the_taxonomy_capability() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category = await _seed_category(uow_factory, tenant_id)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/categories/{category.id}/attribute-definitions",
            json={"key": "fabric", "label": "Fabric", "data_type": "text"},
            headers=headers,
        )

    assert response.status_code == 403


async def test_updating_an_attribute_definition() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category = await _seed_category(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["taxonomy.manage"]
    )

    async with await _client(app) as http:
        create_response = await http.post(
            f"/api/v1/admin/categories/{category.id}/attribute-definitions",
            json={"key": "fabric", "label": "Fabric", "data_type": "text"},
            headers=headers,
        )
        definition_id = create_response.json()["id"]

        update_response = await http.patch(
            f"/api/v1/admin/attribute-definitions/{definition_id}",
            json={"label": "Fabric type", "is_required": True},
            headers=headers,
        )

    assert update_response.status_code == 200
    assert update_response.json()["label"] == "Fabric type"
    assert update_response.json()["is_required"] is True


async def test_creating_an_axis_and_a_value_and_listing_both() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category = await _seed_category(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["taxonomy.manage"]
    )

    async with await _client(app) as http:
        axis_response = await http.post(
            f"/api/v1/admin/categories/{category.id}/variant-axes",
            json={"key": "colour", "label": "Colour", "affects_imagery": True},
            headers=headers,
        )
        assert axis_response.status_code == 201
        axis_id = axis_response.json()["id"]

        value_response = await http.post(
            f"/api/v1/admin/variant-axes/{axis_id}/values",
            json={"value": "maroon", "label": "Maroon"},
            headers=headers,
        )
        assert value_response.status_code == 201

        axes_list = await http.get(
            f"/api/v1/admin/categories/{category.id}/variant-axes", headers=headers
        )
        values_list = await http.get(
            f"/api/v1/admin/variant-axes/{axis_id}/values", headers=headers
        )

    assert [a["key"] for a in axes_list.json()] == ["colour"]
    assert [v["value"] for v in values_list.json()] == ["maroon"]


async def test_updating_a_variant_axis_value() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category = await _seed_category(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["taxonomy.manage"]
    )

    async with await _client(app) as http:
        axis_response = await http.post(
            f"/api/v1/admin/categories/{category.id}/variant-axes",
            json={"key": "colour", "label": "Colour", "affects_imagery": True},
            headers=headers,
        )
        axis_id = axis_response.json()["id"]
        value_response = await http.post(
            f"/api/v1/admin/variant-axes/{axis_id}/values",
            json={"value": "maroon", "label": "Maroon"},
            headers=headers,
        )
        value_id = value_response.json()["id"]

        update_response = await http.patch(
            f"/api/v1/admin/variant-axis-values/{value_id}",
            json={"label": "Deep Maroon", "metadata": {"hex": "#5c1a1a"}},
            headers=headers,
        )

    assert update_response.status_code == 200
    assert update_response.json()["label"] == "Deep Maroon"
