"""HTTP-level tests for ``/api/v1/admin/products*`` — M4's first routes
reachable from outside a test.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient
from PIL import Image

from app.api.deps.authorization import get_token_issuer
from app.api.deps.object_storage import get_object_storage
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.asset import Asset, AssetKind
from app.entities.attribute_definition import AttributeDataType, AttributeDefinition, SemanticRole
from app.entities.category import Category
from app.entities.category_spec_version import CategorySpecVersion
from app.entities.product import Product
from app.entities.product_input_image import ProductInputImage
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.ids import (
    TenantId,
    new_category_id,
    new_input_image_slot_id,
    new_product_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.object_storage import InMemoryObjectStorage
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _build() -> tuple[
    object, FakeUnitOfWorkFactory, FakeClock, AccessTokenCodec, InMemoryObjectStorage
]:
    settings = Settings(
        environment="test", log_format="console", access_token_signing_key=SIGNING_KEY
    )
    app = create_app(settings)
    uow_factory = FakeUnitOfWorkFactory()
    clock = FakeClock(_NOW)
    codec = AccessTokenCodec(SIGNING_KEY)
    storage = InMemoryObjectStorage()
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_token_issuer] = lambda: codec
    app.dependency_overrides[get_object_storage] = lambda: storage
    return app, uow_factory, clock, codec, storage


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
    app, uow_factory, _clock, codec, _storage = _build()
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
    app, uow_factory, _clock, codec, _storage = _build()
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
    app, _uow_factory, _clock, codec, _storage = _build()
    tenant_id_str = str(new_tenant_id())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/products/{uuid.uuid4()}/recompute-readiness", headers=headers
        )

    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


def _sharp_jpeg_bytes(size: int = 800) -> bytes:
    image = Image.new("L", (size, size))
    pixels = image.load()
    square = 20
    for y in range(size):
        for x in range(size):
            pixels[x, y] = 255 if (x // square + y // square) % 2 == 0 else 0
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG")
    return buf.getvalue()


async def test_creating_a_product_over_http_promotes_semantic_columns() -> None:
    app, uow_factory, _clock, codec, _storage = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    user_id = new_user_id()
    category = Category.create(
        tenant_id, key="dresses", name="Dresses", slug="dresses", parent=None, now=_NOW
    )
    await uow_factory.attribute_definitions.add(
        AttributeDefinition.create(
            tenant_id,
            category.id,
            key="product_title",
            label="Title",
            data_type=AttributeDataType.TEXT,
            semantic_role=SemanticRole.TITLE,
            is_required=True,
            now=_NOW,
        )
    )
    spec_version = CategorySpecVersion.create(
        tenant_id,
        category.id,
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
    category.current_spec_version = 1
    await uow_factory.categories.add(category)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/admin/products",
            json={"category_id": str(category.id), "attributes": {"product_title": "A Dress"}},
            headers=headers,
        )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "A Dress"
    assert body["status"] == "draft"


async def test_creating_a_product_variant_over_http_validates_axis_values() -> None:
    app, uow_factory, _clock, codec, _storage = _build()
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
            "variant_axes": [
                {
                    "id": str(uuid.uuid4()),
                    "category_id": str(category_id),
                    "key": "colour",
                    "label": "Colour",
                    "position": 0,
                    "affects_imagery": True,
                    "values": [
                        {
                            "id": str(uuid.uuid4()),
                            "value": "maroon",
                            "label": "Maroon",
                            "metadata": {},
                        }
                    ],
                }
            ],
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
        ok = await http.post(
            f"/api/v1/admin/products/{product.id}/variants",
            json={"axis_values": {"colour": "maroon"}},
            headers=headers,
        )
        rejected = await http.post(
            f"/api/v1/admin/products/{product.id}/variants",
            json={"axis_values": {"colour": "gold"}},
            headers=headers,
        )

    assert ok.status_code == 201
    assert ok.json()["axis_values"] == {"colour": "maroon"}
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "validation_error"


async def test_validating_an_input_image_over_http_reaches_ready() -> None:
    app, uow_factory, _clock, codec, storage = _build()
    tenant_id_str = str(new_tenant_id())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    data = _sharp_jpeg_bytes()
    storage_key = storage.new_storage_key(tenant_id, kind="input", extension="jpg")
    await storage.write(storage_key, data)
    asset = Asset.create(
        tenant_id,
        storage_key=storage_key,
        sha256="a" * 64,
        mime="image/jpeg",
        width=800,
        height=800,
        bytes_=len(data),
        kind=AssetKind.INPUT,
        source="upload",
        now=_NOW,
    )
    await uow_factory.assets.add(asset)
    image = ProductInputImage.create(
        tenant_id,
        new_product_id(),
        input_image_slot_id=new_input_image_slot_id(),
        asset_id=asset.id,
        created_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.product_input_images.add(image)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/input-images/{image.id}/validate", headers=headers
        )

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
