"""``PublicCacheHeadersMiddleware`` — M8's Gate second bullet: cache headers
must not let a tenant-specific response leak to another tenant.
``Vary: Host`` is the property under test, not a full CDN simulation: this
suite proves the header is present and correctly scoped, and that two
tenants resolved through the same path genuinely get different bodies (and
therefore different ``ETag``s) — the fact ``Vary: Host`` exists is what
tells a real cache in front of this API that those two responses must
never share a cache entry.
"""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.api.deps.object_storage import get_object_storage
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.asset import Asset, AssetKind
from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.entities.category import Category
from app.entities.product import Product, ProductStatus
from app.entities.product_variant import ProductVariant
from app.entities.tenant_domain import TenantDomain
from app.shared.ids import (
    new_catalog_image_slot_id,
    new_category_id,
    new_category_spec_version_id,
    new_generation_item_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.object_storage import InMemoryObjectStorage
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _build() -> tuple[object, FakeUnitOfWorkFactory]:
    settings = Settings(
        environment="test", log_format="console", access_token_signing_key=SIGNING_KEY
    )
    app = create_app(settings)
    uow_factory = FakeUnitOfWorkFactory()
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_clock] = lambda: FakeClock(_NOW)
    app.dependency_overrides[get_object_storage] = lambda: InMemoryObjectStorage()
    return app, uow_factory


async def _client(app: object) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_a_public_response_carries_vary_host_and_cache_control() -> None:
    app, uow_factory = _build()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_id, "shop.example.com", now=_NOW)
    )

    async with await _client(app) as http:
        response = await http.get("/api/v1/public/categories", headers={"Host": "shop.example.com"})

    assert response.headers["vary"] == "Host"
    assert "public" in response.headers["cache-control"]
    assert response.headers["etag"]


async def test_admin_responses_carry_no_public_cache_headers() -> None:
    """Proves the middleware's scope, not just its behaviour where applied
    — a route outside ``/public/`` must be untouched."""
    app, _uow = _build()

    async with await _client(app) as http:
        # No auth header at all - a 401 still passes through the same
        # middleware stack, and still must carry none of these headers.
        response = await http.get("/api/v1/admin/settings/approval.required")

    assert "vary" not in response.headers
    assert "etag" not in response.headers


async def test_two_tenants_resolved_through_the_same_path_get_different_etags() -> None:
    app, uow_factory = _build()
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_a, "a-shop.example.com", now=_NOW)
    )
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_b, "b-shop.example.com", now=_NOW)
    )
    await uow_factory.categories.add(
        Category.create(
            tenant_a, key="apparel", name="Apparel", slug="a-apparel", parent=None, now=_NOW
        )
    )
    await uow_factory.categories.add(
        Category.create(
            tenant_b, key="apparel", name="Apparel", slug="b-apparel", parent=None, now=_NOW
        )
    )

    async with await _client(app) as http:
        response_a = await http.get(
            "/api/v1/public/categories", headers={"Host": "a-shop.example.com"}
        )
        response_b = await http.get(
            "/api/v1/public/categories", headers={"Host": "b-shop.example.com"}
        )

    assert response_a.headers["etag"] != response_b.headers["etag"]


async def test_a_matching_if_none_match_gets_a_304_with_no_body() -> None:
    app, uow_factory = _build()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_id, "shop.example.com", now=_NOW)
    )

    async with await _client(app) as http:
        first = await http.get("/api/v1/public/categories", headers={"Host": "shop.example.com"})
        etag = first.headers["etag"]

        second = await http.get(
            "/api/v1/public/categories",
            headers={"Host": "shop.example.com", "If-None-Match": etag},
        )

    assert second.status_code == 304
    assert second.content == b""


async def test_a_404_carries_no_public_cache_headers() -> None:
    app, _uow = _build()

    async with await _client(app) as http:
        response = await http.get(
            "/api/v1/public/categories", headers={"Host": "unregistered.example.com"}
        )

    assert response.status_code == 404
    assert "etag" not in response.headers


async def test_the_images_route_is_private_not_public() -> None:
    """A presigned download URL is a credential embedded in the body, not
    plain catalogue data — a shared cache must never store or redistribute
    it, so this route must not carry ``Cache-Control: public`` even though
    every other ``/public/`` route does."""
    app, uow_factory = _build()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_id, "shop.example.com", now=_NOW)
    )
    product = Product.create(
        tenant_id,
        new_category_id(),
        new_category_spec_version_id(),
        attributes={},
        created_by=new_user_id(),
        now=_NOW,
    )
    product.status = ProductStatus.PUBLISHED
    await uow_factory.products.add(product)
    variant = ProductVariant.create(
        tenant_id, product.id, axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)
    asset = Asset.create(
        tenant_id,
        storage_key="tenant/generated/img.jpg",
        sha256="a" * 64,
        mime="image/jpeg",
        width=800,
        height=800,
        bytes_=1024,
        kind=AssetKind.GENERATED,
        source="pipeline",
        now=_NOW,
    )
    await uow_factory.assets.add(asset)
    image = CatalogImage.create(
        tenant_id,
        variant.id,
        new_catalog_image_slot_id(),
        asset.id,
        new_generation_item_id(),
        now=_NOW,
    )
    image.status = CatalogImageStatus.APPROVED
    await uow_factory.catalog_images.add(image)

    async with await _client(app) as http:
        response = await http.get(
            f"/api/v1/public/products/{product.id}/images", headers={"Host": "shop.example.com"}
        )

    assert response.status_code == 200
    assert "private" in response.headers["cache-control"]
    assert "public" not in response.headers["cache-control"]
