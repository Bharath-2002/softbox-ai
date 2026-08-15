from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.product_variant import ProductVariant
from app.entities.publication import Publication
from app.entities.social_account import SocialAccount
from app.features.publishing.complete_publication_metrics_fetch import (
    CompletePublicationMetricsFetch,
)
from app.services.ports.channel_publisher import ChannelMetrics
from app.shared.errors import NotFoundError
from app.shared.ids import (
    PublicationId,
    new_product_id,
    new_publication_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed_published(uow_factory: FakeUnitOfWorkFactory) -> tuple[object, Publication]:
    tenant_id = new_tenant_id()
    variant = ProductVariant.create(
        tenant_id, new_product_id(), axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)
    channel = SocialAccount.create(
        tenant_id, provider="instagram", external_account_id="ig-1", display_name="Shop", now=_NOW
    )
    await uow_factory.social_accounts.add(channel)
    publication = Publication.create(
        tenant_id,
        variant.id,
        channel.id,
        content_draft_id=None,
        payload={"caption": "x", "media_asset_ids": [], "link": None},
        now=_NOW,
    )
    publication.mark_dispatching(now=_NOW)
    publication.mark_published(external_post_id="post-1", permalink=None, now=_NOW)
    await uow_factory.publications.add(publication)
    return tenant_id, publication


async def test_records_metrics_on_the_publication() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed_published(uow_factory)
    use_case = CompletePublicationMetricsFetch(uow_factory, FakeClock(_NOW))
    metrics = ChannelMetrics(impressions=100, likes=5, clicks=2)

    result = await use_case(tenant_id=tenant_id, publication_id=publication.id, metrics=metrics)

    assert result.metrics == {"impressions": 100, "likes": 5, "clicks": 2}
    stored = await uow_factory.publications.get(tenant_id, publication.id)
    assert stored is not None
    assert stored.metrics == {"impressions": 100, "likes": 5, "clicks": 2}


async def test_an_unknown_publication_is_not_found() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = CompletePublicationMetricsFetch(uow_factory, FakeClock(_NOW))

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            publication_id=PublicationId(new_publication_id()),
            metrics=ChannelMetrics(impressions=None, likes=None, clicks=None),
        )
