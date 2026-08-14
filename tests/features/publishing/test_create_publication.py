from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.content_draft import ContentDraft
from app.entities.product_variant import ProductVariant
from app.entities.social_account import SocialAccount
from app.features.publishing.create_publication import CreatePublication
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import (
    AssetId,
    ContentDraftId,
    ProductVariantId,
    SocialAccountId,
    new_asset_id,
    new_content_draft_id,
    new_product_id,
    new_social_account_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[CreatePublication, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return CreatePublication(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed_variant_and_channel(
    uow_factory: FakeUnitOfWorkFactory,
) -> tuple[object, ProductVariantId, SocialAccountId]:
    tenant_id = new_tenant_id()
    variant = ProductVariant.create(
        tenant_id, new_product_id(), axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)
    channel = SocialAccount.create(
        tenant_id, provider="instagram", external_account_id="ig-1", display_name="Shop", now=_NOW
    )
    await uow_factory.social_accounts.add(channel)
    return tenant_id, variant.id, channel.id


async def test_creating_a_publication_commits_the_row_and_writes_the_outbox_event() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, channel_id = await _seed_variant_and_channel(uow_factory)

    publication = await use_case(
        tenant_id=tenant_id,
        variant_id=variant_id,
        channel_id=channel_id,
        content_draft_id=None,
        caption="Crafted with care.",
        media_asset_ids=[AssetId(new_asset_id())],
    )

    assert publication.status.value == "pending"
    assert publication.idempotency_key
    stored = await uow_factory.publications.get(tenant_id, publication.id)
    assert stored is not None
    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert len(events) == 1
    assert events[0].event_type == "publication.publish_requested"
    assert events[0].payload == {"publication_id": str(publication.id)}


async def test_an_unknown_variant_is_not_found() -> None:
    use_case, uow_factory = _use_case()
    _tenant_id, _variant_id, channel_id = await _seed_variant_and_channel(uow_factory)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            variant_id=ProductVariantId(new_product_id()),
            channel_id=channel_id,
            content_draft_id=None,
            caption="x",
            media_asset_ids=[AssetId(new_asset_id())],
        )


async def test_an_unknown_channel_is_not_found() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, _channel_id = await _seed_variant_and_channel(uow_factory)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            variant_id=variant_id,
            channel_id=SocialAccountId(new_social_account_id()),
            content_draft_id=None,
            caption="x",
            media_asset_ids=[AssetId(new_asset_id())],
        )


async def test_no_media_assets_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, channel_id = await _seed_variant_and_channel(uow_factory)

    with pytest.raises(ValidationError):
        await use_case(
            tenant_id=tenant_id,
            variant_id=variant_id,
            channel_id=channel_id,
            content_draft_id=None,
            caption="x",
            media_asset_ids=[],
        )


async def test_an_unapproved_content_draft_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, channel_id = await _seed_variant_and_channel(uow_factory)
    draft = ContentDraft.create(
        tenant_id,
        variant_id,
        channel="instagram",
        locale="en",
        body="Crafted with care.",
        alt_text="A folded saree.",
        model="fake-text-model",
        prompt_version="v1",
        now=_NOW,
    )
    await uow_factory.content_drafts.add(draft)

    with pytest.raises(ValidationError):
        await use_case(
            tenant_id=tenant_id,
            variant_id=variant_id,
            channel_id=channel_id,
            content_draft_id=draft.id,
            caption="x",
            media_asset_ids=[AssetId(new_asset_id())],
        )


async def test_an_unknown_content_draft_is_not_found() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, channel_id = await _seed_variant_and_channel(uow_factory)

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=tenant_id,
            variant_id=variant_id,
            channel_id=channel_id,
            content_draft_id=ContentDraftId(new_content_draft_id()),
            caption="x",
            media_asset_ids=[AssetId(new_asset_id())],
        )
