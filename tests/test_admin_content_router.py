"""HTTP-level tests for D23's copy-generation endpoints:
``POST /api/v1/admin/variants/{id}/content-drafts`` (enqueue) and
``POST /api/v1/admin/content/generate-next`` (the worker step) - the same
known-interim "real capability, no automatic trigger" shape
``POST .../generation/render-next``/``qc-next`` already use.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import get_token_issuer
from app.api.deps.text_generation import get_text_generation
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.catalog_image import CatalogImage
from app.entities.category import Category
from app.entities.content_draft import ContentDraft
from app.entities.product import Product
from app.entities.product_variant import ProductVariant
from app.entities.setting import Setting, SettingScope
from app.features.content.start_content_draft_generation import JOB_TYPE
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.ids import (
    TenantId,
    new_asset_id,
    new_catalog_image_slot_id,
    new_category_spec_version_id,
    new_generation_item_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.text_generation import FakeTextGeneration
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _build() -> tuple[
    object, FakeUnitOfWorkFactory, FakeClock, AccessTokenCodec, FakeTextGeneration
]:
    settings = Settings(
        environment="test", log_format="console", access_token_signing_key=SIGNING_KEY
    )
    app = create_app(settings)
    uow_factory = FakeUnitOfWorkFactory()
    clock = FakeClock(_NOW)
    codec = AccessTokenCodec(SIGNING_KEY)
    text_generation = FakeTextGeneration()
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_token_issuer] = lambda: codec
    app.dependency_overrides[get_text_generation] = lambda: text_generation
    return app, uow_factory, clock, codec, text_generation


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


async def _seed_variant_with_approved_image(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: TenantId
) -> ProductVariant:
    category = Category.create(
        tenant_id, key="sarees", name="Sarees", slug="sarees", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)
    product = Product.create(
        tenant_id,
        category.id,
        new_category_spec_version_id(),
        attributes={"colour": "red"},
        created_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.products.add(product)
    variant = ProductVariant.create(
        tenant_id, product.id, axis_values={}, created_by=new_user_id(), now=_NOW
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
    image.mark_qc_passed(qc_result={}, now=_NOW)
    image.approve(approved_by=new_user_id(), now=_NOW)
    await uow_factory.catalog_images.add(image)
    return variant


async def test_generate_over_http_enqueues_and_returns_202() -> None:
    app, uow_factory, _clock, codec, _text_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    variant = await _seed_variant_with_approved_image(uow_factory, tenant_id)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/variants/{variant.id}/content-drafts",
            json={"channel": "instagram", "locale": "en"},
            headers=headers,
        )

    assert response.status_code == 202
    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert len(events) == 1
    assert events[0].event_type == "content_draft.generate_requested"


async def test_generate_next_over_http_claims_and_returns_the_draft() -> None:
    app, uow_factory, _clock, codec, _text_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    variant = await _seed_variant_with_approved_image(uow_factory, tenant_id)
    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={
            "variant_id": str(variant.id),
            "channel": "instagram",
            "locale": "en",
            "model": "fake-text-model",
        },
        run_at=_NOW,
        now=_NOW,
    )
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post("/api/v1/admin/content/generate-next", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body is not None
    assert body["status"] == "pending_approval"
    assert body["variant_id"] == str(variant.id)


async def test_generate_next_over_http_returns_null_when_nothing_is_claimable() -> None:
    app, _uow_factory, _clock, codec, _text_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post("/api/v1/admin/content/generate-next", headers=headers)

    assert response.status_code == 200
    assert response.json() is None


async def test_generate_requires_the_product_manage_capability() -> None:
    app, _uow_factory, _clock, codec, _text_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/variants/{uuid.uuid4()}/content-drafts",
            json={"channel": "instagram", "locale": "en"},
            headers=headers,
        )

    assert response.status_code == 403


async def _seed_pending_approval_draft(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: TenantId
) -> tuple[ContentDraft, ProductVariant]:
    variant = await _seed_variant_with_approved_image(uow_factory, tenant_id)
    draft = ContentDraft.create(
        tenant_id,
        variant.id,
        channel="instagram",
        locale="en",
        body="Crafted with care.",
        alt_text="A folded saree.",
        model="fake-text-model",
        prompt_version="v1",
        now=_NOW,
    )
    draft.mark_pending_approval(now=_NOW)
    await uow_factory.content_drafts.add(draft)
    return draft, variant


async def test_list_content_drafts_over_http_returns_the_live_draft() -> None:
    app, uow_factory, _clock, codec, _text_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    draft, variant = await _seed_pending_approval_draft(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["catalog.approve"]
    )

    async with await _client(app) as http:
        response = await http.get(
            f"/api/v1/admin/variants/{variant.id}/content-drafts", headers=headers
        )

    assert response.status_code == 200
    body = response.json()
    assert [d["id"] for d in body] == [str(draft.id)]


async def test_approve_content_draft_over_http_marks_it_approved() -> None:
    app, uow_factory, _clock, codec, _text_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    draft, _variant = await _seed_pending_approval_draft(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["catalog.approve"]
    )

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/content-drafts/{draft.id}/approve", headers=headers
        )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    stored = await uow_factory.content_drafts.get(tenant_id, draft.id)
    assert stored is not None
    assert stored.status.value == "approved"


async def test_reject_content_draft_over_http_records_the_reason() -> None:
    app, uow_factory, _clock, codec, _text_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    draft, _variant = await _seed_pending_approval_draft(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["catalog.approve"]
    )

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/content-drafts/{draft.id}/reject",
            json={"reason": "wrong tone"},
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
    assert response.json()["rejection_reason"] == "wrong tone"


async def test_approve_content_draft_requires_the_catalog_approve_capability() -> None:
    app, uow_factory, _clock, codec, _text_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    draft, _variant = await _seed_pending_approval_draft(uow_factory, tenant_id)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/content-drafts/{draft.id}/approve", headers=headers
        )

    assert response.status_code == 403


async def test_edit_content_draft_over_http_supersedes_and_returns_the_replacement() -> None:
    app, uow_factory, _clock, codec, _text_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    draft, _variant = await _seed_pending_approval_draft(uow_factory, tenant_id)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.patch(
            f"/api/v1/admin/content-drafts/{draft.id}",
            json={"body": "Hand-edited copy.", "hashtags": [], "alt_text": "A folded saree."},
            headers=headers,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] != str(draft.id)
    assert body["body"] == "Hand-edited copy."
    assert body["status"] == "pending_approval"
    stored_original = await uow_factory.content_drafts.get(tenant_id, draft.id)
    assert stored_original is not None
    assert stored_original.superseded_by is not None


async def test_edit_content_draft_requires_the_product_manage_capability() -> None:
    app, uow_factory, _clock, codec, _text_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    draft, _variant = await _seed_pending_approval_draft(uow_factory, tenant_id)
    headers = _bearer(
        codec, tenant_id=tenant_id_str, role="admin", capabilities=["catalog.approve"]
    )

    async with await _client(app) as http:
        response = await http.patch(
            f"/api/v1/admin/content-drafts/{draft.id}",
            json={"body": "Hand-edited copy.", "hashtags": [], "alt_text": "A folded saree."},
            headers=headers,
        )

    assert response.status_code == 403


async def test_edit_content_draft_over_http_rejects_a_forbidden_claim() -> None:
    app, uow_factory, _clock, codec, _text_generation = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    draft, _variant = await _seed_pending_approval_draft(uow_factory, tenant_id)
    await uow_factory.settings.add(
        Setting.create(
            scope_type=SettingScope.TENANT,
            tenant_id=tenant_id,
            scope_id=None,
            key="content.forbidden_claims",
            value=["cures arthritis"],
            now=_NOW,
        )
    )
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.patch(
            f"/api/v1/admin/content-drafts/{draft.id}",
            json={
                "body": "This saree cures arthritis.",
                "hashtags": [],
                "alt_text": "A folded saree.",
            },
            headers=headers,
        )

    assert response.status_code == 422
    stored = await uow_factory.content_drafts.get(tenant_id, draft.id)
    assert stored is not None
    assert stored.superseded_by is None
