"""HTTP-level tests for ``/api/v1/admin/catalog-images/*`` and
``/api/v1/admin/products/{id}/catalog-images/approve-all`` (M6) — the
approval queue. All gated on ``catalog.approve``, not ``product.manage``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import get_token_issuer
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.catalog_image import CatalogImage
from app.entities.product import Product
from app.entities.product_variant import ProductVariant
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.ids import (
    ProductId,
    TenantId,
    new_asset_id,
    new_catalog_image_slot_id,
    new_category_id,
    new_category_spec_version_id,
    new_generation_item_id,
    new_user_id,
)
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


async def _seed_pending_approval(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: TenantId
) -> tuple[CatalogImage, ProductId]:
    product = Product.create(
        tenant_id,
        new_category_id(),
        new_category_spec_version_id(),
        attributes={},
        created_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.products.add(product)
    product_id = product.id
    variant = ProductVariant.create(
        tenant_id, product_id, axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)
    image = CatalogImage.create(
        tenant_id,
        variant.id,
        new_catalog_image_slot_id(),
        new_asset_id(),
        new_generation_item_id(),
        now=_NOW,
    )
    image.mark_qc_passed(qc_result={"subject_present": True}, now=_NOW)
    await uow_factory.catalog_images.add(image)
    return image, product_id


async def test_list_over_http_returns_a_pending_approval_image() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    image, _product_id = await _seed_pending_approval(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["catalog.approve"]
    )

    async with await _client(app) as http:
        response = await http.get("/api/v1/admin/catalog-images", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert [i["id"] for i in body["items"]] == [str(image.id)]


async def test_approve_over_http_marks_the_image_approved() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    image, _product_id = await _seed_pending_approval(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["catalog.approve"]
    )

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/catalog-images/{image.id}/approve", headers=headers
        )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    stored = await uow_factory.catalog_images.get(tenant_id, image.id)
    assert stored is not None
    assert stored.status.value == "approved"


async def test_reject_over_http_records_the_reason() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    image, _product_id = await _seed_pending_approval(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["catalog.approve"]
    )

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/catalog-images/{image.id}/reject",
            json={"reason": "motif is wrong"},
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["rejection_reason"] == "motif is wrong"


async def test_bulk_approve_over_http_approves_every_pending_image_for_the_product() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    image, product_id = await _seed_pending_approval(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["catalog.approve"]
    )

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/products/{product_id}/catalog-images/approve-all", headers=headers
        )

    assert response.status_code == 200
    assert response.json() == {"approved": 1}
    stored = await uow_factory.catalog_images.get(tenant_id, image.id)
    assert stored is not None
    assert stored.status.value == "approved"


async def test_bulk_approve_for_an_unknown_product_is_not_found() -> None:
    app, _uow_factory, _clock, codec = _build()
    tenant_id_str = str(uuid.uuid4())
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["catalog.approve"]
    )

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/products/{uuid.uuid4()}/catalog-images/approve-all", headers=headers
        )

    assert response.status_code == 404


async def test_list_requires_the_catalog_approve_capability() -> None:
    app, _uow_factory, _clock, codec = _build()
    tenant_id_str = str(uuid.uuid4())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.get("/api/v1/admin/catalog-images", headers=headers)

    assert response.status_code == 403


async def test_approve_requires_the_catalog_approve_capability_not_product_manage() -> None:
    app, uow_factory, _clock, codec = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    image, _product_id = await _seed_pending_approval(uow_factory, tenant_id)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/catalog-images/{image.id}/approve", headers=headers
        )

    assert response.status_code == 403
