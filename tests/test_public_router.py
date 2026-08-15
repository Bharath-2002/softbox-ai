"""HTTP-level tests for ``/api/v1/public/*`` (D4, M8) — no bearer token,
tenant resolved from the ``Host`` header instead.

``test_a_tenants_storefront_never_returns_another_tenants_category`` is
M8's Gate property for this route: resolving tenant A's host must never
surface tenant B's data, proven by seeding both tenants with their own
category and asserting tenant A's response contains only tenant A's.
"""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.category import Category
from app.entities.product import Product, ProductStatus
from app.entities.tenant_domain import TenantDomain
from app.shared.ids import (
    TenantId,
    new_category_id,
    new_category_spec_version_id,
    new_product_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
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
    return app, uow_factory


async def _client(app: object) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_listing_categories_resolves_the_tenant_from_the_host_header() -> None:
    app, uow_factory = _build()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_id, "shop.example.com", now=_NOW)
    )
    category = Category.create(
        tenant_id, key="apparel", name="Apparel", slug="apparel", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)

    async with await _client(app) as http:
        response = await http.get("/api/v1/public/categories", headers={"Host": "shop.example.com"})

    assert response.status_code == 200
    assert [row["slug"] for row in response.json()] == ["apparel"]


async def test_an_unregistered_host_is_not_found() -> None:
    app, _uow = _build()

    async with await _client(app) as http:
        response = await http.get(
            "/api/v1/public/categories", headers={"Host": "unregistered.example.com"}
        )

    assert response.status_code == 404


async def test_a_tenants_storefront_never_returns_another_tenants_category() -> None:
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
        response = await http.get(
            "/api/v1/public/categories", headers={"Host": "a-shop.example.com"}
        )

    slugs = [row["slug"] for row in response.json()]
    assert slugs == ["a-apparel"]
    assert "b-apparel" not in slugs


async def test_the_host_header_port_is_ignored() -> None:
    app, uow_factory = _build()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_id, "shop.example.com", now=_NOW)
    )

    async with await _client(app) as http:
        response = await http.get(
            "/api/v1/public/categories", headers={"Host": "shop.example.com:8443"}
        )

    assert response.status_code == 200


def _published_product(tenant_id: TenantId, title: str) -> Product:
    product = Product.create(
        tenant_id,
        new_category_id(),
        new_category_spec_version_id(),
        attributes={},
        created_by=new_user_id(),
        now=_NOW,
        title=title,
    )
    product.status = ProductStatus.PUBLISHED
    return product


async def test_listing_products_only_returns_published_ones() -> None:
    app, uow_factory = _build()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_id, "shop.example.com", now=_NOW)
    )
    published = _published_product(tenant_id, "Maroon silk saree")
    draft = Product.create(
        tenant_id,
        new_category_id(),
        new_category_spec_version_id(),
        attributes={},
        created_by=new_user_id(),
        now=_NOW,
        title="Unfinished listing",
    )
    await uow_factory.products.add(published)
    await uow_factory.products.add(draft)

    async with await _client(app) as http:
        response = await http.get("/api/v1/public/products", headers={"Host": "shop.example.com"})

    titles = [row["title"] for row in response.json()["items"]]
    assert titles == ["Maroon silk saree"]


async def test_getting_a_published_product_by_id() -> None:
    app, uow_factory = _build()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_id, "shop.example.com", now=_NOW)
    )
    product = _published_product(tenant_id, "Maroon silk saree")
    await uow_factory.products.add(product)

    async with await _client(app) as http:
        response = await http.get(
            f"/api/v1/public/products/{product.id}", headers={"Host": "shop.example.com"}
        )

    assert response.status_code == 200
    assert response.json()["title"] == "Maroon silk saree"


async def test_a_tenants_storefront_never_returns_another_tenants_product_by_id() -> None:
    """M8's Gate, in its literal wording: resolving tenant A's host and
    requesting tenant B's known product id must not return tenant B's data
    — it must behave exactly as if that id never existed."""
    app, uow_factory = _build()
    tenant_a = new_tenant_id()
    tenant_b = new_tenant_id()
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_a, "a-shop.example.com", now=_NOW)
    )
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_b, "b-shop.example.com", now=_NOW)
    )
    tenant_bs_product = _published_product(tenant_b, "Tenant B's saree")
    await uow_factory.products.add(tenant_bs_product)

    async with await _client(app) as http:
        response = await http.get(
            f"/api/v1/public/products/{tenant_bs_product.id}",
            headers={"Host": "a-shop.example.com"},
        )

    assert response.status_code == 404


async def test_an_unknown_product_id_is_not_found() -> None:
    app, uow_factory = _build()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_domains.add(
        TenantDomain.create(tenant_id, "shop.example.com", now=_NOW)
    )

    async with await _client(app) as http:
        response = await http.get(
            f"/api/v1/public/products/{new_product_id()}", headers={"Host": "shop.example.com"}
        )

    assert response.status_code == 404
