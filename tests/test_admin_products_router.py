"""HTTP-level test for ``/api/v1/admin/products/{id}/recompute-readiness`` —
M4's first route reachable from outside a test.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import get_token_issuer
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.category_spec_version import CategorySpecVersion
from app.entities.product import Product
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


async def test_recomputing_readiness_over_http_marks_a_satisfied_product_ready() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category_id = new_category_id()
    user_id = new_user_id()
    spec_version = CategorySpecVersion.create(
        tenant_id,
        category_id,
        version=1,
        snapshot={
            "attribute_definitions": [],
            "variant_axes": [],
            "input_image_slots": [],
            "catalog_image_slots": [],
        },
        published_by=user_id,
        now=_NOW,
    )
    await uow_factory.category_spec_versions.add(spec_version)
    product = Product.create(
        tenant_id, category_id, spec_version.id, attributes={}, created_by=user_id, now=_NOW
    )
    await uow_factory.products.add(product)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/products/{product.id}/recompute-readiness", headers=headers
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


async def test_recomputing_readiness_requires_the_product_manage_capability() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    category_id = new_category_id()
    user_id = new_user_id()
    spec_version = CategorySpecVersion.create(
        tenant_id,
        category_id,
        version=1,
        snapshot={
            "attribute_definitions": [],
            "variant_axes": [],
            "input_image_slots": [],
            "catalog_image_slots": [],
        },
        published_by=user_id,
        now=_NOW,
    )
    await uow_factory.category_spec_versions.add(spec_version)
    product = Product.create(
        tenant_id, category_id, spec_version.id, attributes={}, created_by=user_id, now=_NOW
    )
    await uow_factory.products.add(product)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/products/{product.id}/recompute-readiness", headers=headers
        )

    assert response.status_code == 403


async def test_recomputing_readiness_for_an_unknown_product_is_not_found() -> None:
    app, _uow_factory, _clock, codec = _build()
    tenant_id_str = str(new_tenant_id())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/products/{uuid.uuid4()}/recompute-readiness", headers=headers
        )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
