"""HTTP-level tests for D21's publish-trigger endpoints:
``POST /api/v1/admin/variants/{id}/publications`` (enqueue) and
``POST /api/v1/admin/publications/publish-next`` (the worker step) - the
same known-interim "real capability, no automatic trigger" shape
``POST .../content/generate-next`` already uses.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import get_token_issuer
from app.api.deps.channel_publisher import get_channel_publisher
from app.api.deps.rate_limit import get_rate_limiter
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.product_variant import ProductVariant
from app.entities.publication import Publication
from app.entities.social_account import SocialAccount
from app.features.publishing.start_publication_publish import JOB_TYPE
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.ids import TenantId, new_asset_id, new_product_id, new_user_id
from tests.fakes.channel_publisher import FakeChannelPublisher
from tests.fakes.clock import FakeClock
from tests.fakes.rate_limiter import InMemoryRateLimiter
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _build() -> tuple[
    object, FakeUnitOfWorkFactory, FakeClock, AccessTokenCodec, FakeChannelPublisher
]:
    settings = Settings(
        environment="test", log_format="console", access_token_signing_key=SIGNING_KEY
    )
    app = create_app(settings)
    uow_factory = FakeUnitOfWorkFactory()
    clock = FakeClock(_NOW)
    codec = AccessTokenCodec(SIGNING_KEY)
    channel_publisher = FakeChannelPublisher()
    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_token_issuer] = lambda: codec
    app.dependency_overrides[get_channel_publisher] = lambda: channel_publisher
    app.dependency_overrides[get_rate_limiter] = lambda: InMemoryRateLimiter()
    return app, uow_factory, clock, codec, channel_publisher


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


async def _seed_variant_and_channel(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: TenantId
) -> tuple[ProductVariant, SocialAccount]:
    variant = ProductVariant.create(
        tenant_id, new_product_id(), axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)
    channel = SocialAccount.create(
        tenant_id, provider="instagram", external_account_id="ig-1", display_name="Shop", now=_NOW
    )
    await uow_factory.social_accounts.add(channel)
    return variant, channel


async def test_create_publication_over_http_returns_202() -> None:
    app, uow_factory, _clock, codec, _channel_publisher = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    variant, channel = await _seed_variant_and_channel(uow_factory, tenant_id)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/variants/{variant.id}/publications",
            json={
                "channel_id": str(channel.id),
                "caption": "Crafted with care.",
                "media_asset_ids": [str(new_asset_id())],
            },
            headers=headers,
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert len(events) == 1
    assert events[0].event_type == "publication.publish_requested"


async def test_a_scheduled_publication_over_http_writes_no_outbox_event_yet() -> None:
    app, uow_factory, _clock, codec, _channel_publisher = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    variant, channel = await _seed_variant_and_channel(uow_factory, tenant_id)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/variants/{variant.id}/publications",
            json={
                "channel_id": str(channel.id),
                "caption": "Crafted with care.",
                "media_asset_ids": [str(new_asset_id())],
                "scheduled_at": (_NOW + timedelta(days=1)).isoformat(),
            },
            headers=headers,
        )

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "scheduled"
    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert events == []


async def test_release_scheduled_publications_over_http_releases_a_due_row() -> None:
    app, uow_factory, clock, codec, _channel_publisher = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    variant, channel = await _seed_variant_and_channel(uow_factory, tenant_id)
    publication = Publication.create(
        tenant_id,
        variant.id,
        channel.id,
        content_draft_id=None,
        payload={"caption": "x", "media_asset_ids": [], "link": None},
        scheduled_at=_NOW + timedelta(hours=1),
        now=_NOW,
    )
    await uow_factory.publications.add(publication)
    clock.advance(timedelta(hours=1))
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post("/api/v1/admin/publications/release-scheduled", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"released": 1}
    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert len(events) == 1


async def test_create_publication_requires_the_product_manage_capability() -> None:
    app, uow_factory, _clock, codec, _channel_publisher = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    variant, channel = await _seed_variant_and_channel(uow_factory, tenant_id)
    headers = _bearer(codec, tenant_id=tenant_id_str, role="viewer", capabilities=[])

    async with await _client(app) as http:
        response = await http.post(
            f"/api/v1/admin/variants/{variant.id}/publications",
            json={
                "channel_id": str(channel.id),
                "caption": "x",
                "media_asset_ids": [str(new_asset_id())],
            },
            headers=headers,
        )

    assert response.status_code == 403


async def test_publish_next_over_http_claims_and_publishes() -> None:
    app, uow_factory, _clock, codec, _channel_publisher = _build()
    tenant_id_str = str(uuid.uuid4())
    tenant_id = TenantId(uuid.UUID(tenant_id_str))
    variant, channel = await _seed_variant_and_channel(uow_factory, tenant_id)
    publication = Publication.create(
        tenant_id,
        variant.id,
        channel.id,
        content_draft_id=None,
        payload={"caption": "Crafted with care.", "media_asset_ids": [], "link": None},
        now=_NOW,
    )
    await uow_factory.publications.add(publication)
    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={"publication_id": str(publication.id)},
        run_at=_NOW,
        now=_NOW,
    )
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post("/api/v1/admin/publications/publish-next", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body is not None
    assert body["status"] == "published"


async def test_publish_next_over_http_returns_null_when_nothing_is_claimable() -> None:
    app, _uow_factory, _clock, codec, _channel_publisher = _build()
    tenant_id_str = str(uuid.uuid4())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post("/api/v1/admin/publications/publish-next", headers=headers)

    assert response.status_code == 200
    assert response.json() is None


async def test_channel_publisher_unavailable_returns_503_when_unset() -> None:
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
    # Deliberately no override for get_channel_publisher - proves the 503
    # path fires when no adapter is configured, the same shape
    # api/deps/text_generation.py's own test coverage already established.
    tenant_id_str = str(uuid.uuid4())
    headers = _bearer(codec, tenant_id=tenant_id_str, role="admin", capabilities=["product.manage"])

    async with await _client(app) as http:
        response = await http.post("/api/v1/admin/publications/publish-next", headers=headers)

    assert response.status_code == 503
