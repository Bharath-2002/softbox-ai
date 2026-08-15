"""Seeds one demo tenant with a real, published product and an approved
catalog image, end to end through the real entity factories and the real
FK chain: category -> published spec version -> catalog image slot ->
catalog template -> product -> variant -> generation request -> generation
item -> asset -> catalog image. Same shapes production code produces, not
raw inserts standing in for them (the only raw insert here is `tenants`
itself — no write port exists for that yet, per
`services.ports.tenant_repository`'s own docstring; every test in this
codebase seeds it the same way).

Exists because `/api/v1/public/*` (M8) needs something real to answer with
locally — the frontend cutover's dev server has nothing to render against
an empty database.

Idempotent at the top level only: if a `tenant_domains` row already exists
for the target hostname, the script prints that tenant's id and exits
without creating anything. Not idempotent within a run beyond that check —
re-running against a hostname that was never registered creates a second,
independent demo tenant rather than erroring, since nothing here assumes
there is only ever one.

Usage:
    uv run python scripts/seed_demo_storefront.py [--hostname HOST]

Connects as the ordinary app role (`SOFTBOX_DATABASE_URL`), the same role a
real request handles as — proves the RLS-bound write path works, not just
an owner-role shortcut.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import shutil
from pathlib import Path

from sqlalchemy import text

from app.bootstrap.settings import Settings
from app.entities.asset import Asset, AssetKind
from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.entities.catalog_template import CatalogTemplate
from app.entities.category import Category
from app.entities.category_spec_version import CategorySpecVersion
from app.entities.generation_item import GenerationItem
from app.entities.generation_request import GenerationRequest
from app.entities.image_slots import CatalogImageSlot
from app.entities.product import Product, ProductStatus
from app.entities.product_variant import ProductVariant
from app.entities.tenant_domain import TenantDomain
from app.infrastructure.persistence.database import create_engine, create_session_factory
from app.infrastructure.persistence.mapping import start_mappers
from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork
from app.services.image_inspection import inspect_image
from app.shared.clock import utcnow
from app.shared.ids import new_tenant_id, new_user_id

_SOURCE_IMAGE = (
    Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "collections" / "1.jpeg"
)

_INSERT_TENANT = text(
    "INSERT INTO tenants (id, name, slug, status, plan, created_at, updated_at) "
    "VALUES (:id, :name, :slug, 'active', 'demo', now(), now())"
)
_INSERT_USER = text(
    "INSERT INTO users (id, email, email_verified, display_name, status, created_at, updated_at) "
    "VALUES (:id, :email, true, :display_name, 'active', now(), now())"
)


async def _seed(hostname: str) -> None:
    start_mappers()
    settings = Settings()
    engine = create_engine(settings.database_url.get_secret_value())
    session_factory = create_session_factory(engine)

    async with SqlUnitOfWork(session_factory, None) as uow:
        existing = await uow.tenant_domains.resolve_by_hostname(hostname)
    if existing is not None:
        print(f"'{hostname}' already resolves to tenant {existing.tenant_id} - nothing to do.")
        await engine.dispose()
        return

    now = utcnow()
    tenant_id = new_tenant_id()
    user_id = new_user_id()

    async with SqlUnitOfWork(session_factory, None) as uow:
        await uow.session.execute(
            _INSERT_TENANT,
            {
                "id": str(tenant_id),
                "name": "Baby Sarees (demo)",
                "slug": f"demo-{tenant_id.hex[:8]}",
            },
        )
        await uow.session.execute(
            _INSERT_USER,
            {
                "id": str(user_id),
                "email": f"demo-seed-{user_id.hex[:8]}@example.com",
                "display_name": "Demo Seed",
            },
        )

    async with SqlUnitOfWork(session_factory, tenant_id) as uow:
        await uow.tenant_domains.add(TenantDomain.create(tenant_id, hostname, now=now))

        category = Category.create(
            tenant_id,
            key="handloom-sarees",
            name="Handloom Sarees",
            slug="handloom-sarees",
            parent=None,
            description="Hand-woven sarees in traditional weaves.",
            now=now,
        )
        await uow.categories.add(category)

        spec_version = CategorySpecVersion.create(
            tenant_id, category.id, version=1, snapshot={}, published_by=user_id, now=now
        )
        await uow.category_spec_versions.add(spec_version)

        slot = CatalogImageSlot.create(
            tenant_id,
            category.id,
            key="front",
            label="Front view",
            aspect_ratio="4:5",
            target_width=1200,
            target_height=1500,
            now=now,
        )
        await uow.catalog_image_slots.add(slot)

        image_bytes = _SOURCE_IMAGE.read_bytes()
        inspected = inspect_image(image_bytes)
        sha256 = hashlib.sha256(image_bytes).hexdigest()
        storage_key = f"tenants/{tenant_id}/generated/{sha256}.jpg"
        destination = Path(settings.object_storage_local_root) / storage_key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_SOURCE_IMAGE, destination)

        asset = Asset.create(
            tenant_id,
            storage_key=storage_key,
            sha256=sha256,
            mime=inspected.mime,
            width=inspected.width,
            height=inspected.height,
            bytes_=len(image_bytes),
            kind=AssetKind.GENERATED,
            source="seed_demo_storefront",
            now=now,
        )
        await uow.assets.add(asset)

        template = CatalogTemplate.create_from_upload(
            tenant_id,
            slot.id,
            name="Front view - plain background",
            source_asset_id=asset.id,
            created_by=user_id,
            now=now,
            is_default=True,
        )
        await uow.catalog_templates.add(template)

        product = Product.create(
            tenant_id,
            category.id,
            spec_version.id,
            attributes={"colour": "Maroon", "fabric": "Silk"},
            created_by=user_id,
            now=now,
            title="Maroon Silk Handloom Saree",
            sku="DEMO-SAR-001",
            price_amount=185000,
            price_currency="INR",
        )
        product.status = ProductStatus.PUBLISHED
        await uow.products.add(product)

        variant = ProductVariant.create(
            tenant_id, product.id, axis_values={}, created_by=user_id, now=now, is_default=True
        )
        await uow.product_variants.add(variant)

        request = GenerationRequest.create(
            tenant_id,
            product.id,
            variant.id,
            spec_version.id,
            settings_snapshot={},
            quota_reservation_id=None,
            requested_by=user_id,
            now=now,
        )
        await uow.generation_requests.add(request)

        item = GenerationItem.create(
            tenant_id,
            request.id,
            slot.id,
            template.id,
            attempt_no=1,
            provider="seed",
            model="seed",
            model_params={},
            seed=0,
            prompt_rendered="seed",
            prompt_version="seed",
            input_asset_ids=[asset.id],
            now=now,
        )
        await uow.generation_items.add(item)

        catalog_image = CatalogImage.create(
            tenant_id, variant.id, slot.id, asset.id, item.id, now=now, is_primary=True
        )
        catalog_image.status = CatalogImageStatus.APPROVED
        await uow.catalog_images.add(catalog_image)

    await engine.dispose()
    print(f"Seeded tenant {tenant_id} - '{hostname}' now resolves to it.")
    print(f"Product: {product.title} ({product.id})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hostname", default="localhost")
    args = parser.parse_args()
    asyncio.run(_seed(args.hostname))


if __name__ == "__main__":
    main()
