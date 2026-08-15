"""Exercises `agents.publication_metrics.PublicationMetricsAgent` with the
real `Start`/`CompletePublicationMetricsFetch` use cases wired together
the way `bootstrap/di.py` wires them — only `ChannelPublisher` is a fake.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.agents.publication_metrics import PublicationMetricsAgent
from app.entities.product_variant import ProductVariant
from app.entities.publication import Publication, PublicationStatus
from app.entities.social_account import SocialAccount
from app.features.publishing.complete_publication_metrics_fetch import (
    CompletePublicationMetricsFetch,
)
from app.features.publishing.start_publication_metrics_fetch import (
    StartPublicationMetricsFetch,
)
from app.services.ports.channel_publisher import ChannelMetrics
from app.shared.ids import new_product_id, new_tenant_id, new_user_id
from tests.fakes.channel_publisher import FakeChannelPublisher
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _agent(
    uow_factory: FakeUnitOfWorkFactory, channel_publisher: FakeChannelPublisher, clock: FakeClock
) -> PublicationMetricsAgent:
    return PublicationMetricsAgent(
        StartPublicationMetricsFetch(uow_factory, clock),
        CompletePublicationMetricsFetch(uow_factory, clock),
        channel_publisher,
    )


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


async def test_a_normal_fetch_records_metrics() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed_published(uow_factory)
    channel_publisher = FakeChannelPublisher()
    channel_publisher.next_metrics = ChannelMetrics(impressions=42, likes=3, clicks=1)
    agent = _agent(uow_factory, channel_publisher, FakeClock(_NOW))

    result = await agent.run(tenant_id=tenant_id)

    assert result is not None
    assert result.metrics == {"impressions": 42, "likes": 3, "clicks": 1}
    assert channel_publisher.metrics_calls == ["post-1"]
    stored = await uow_factory.publications.get(tenant_id, publication.id)
    assert stored is not None
    assert stored.metrics == {"impressions": 42, "likes": 3, "clicks": 1}


async def test_a_provider_failure_is_swallowed_not_raised() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed_published(uow_factory)
    channel_publisher = FakeChannelPublisher()
    channel_publisher.next_metrics_error = TimeoutError("provider unreachable")
    agent = _agent(uow_factory, channel_publisher, FakeClock(_NOW))

    result = await agent.run(tenant_id=tenant_id)

    assert result is None
    stored = await uow_factory.publications.get(tenant_id, publication.id)
    assert stored is not None
    assert stored.status is PublicationStatus.PUBLISHED  # untouched, still no metrics
    assert stored.metrics is None
    # the claim step still bumped metrics_fetched_at - the row won't be
    # immediately re-selected within the same staleness window
    assert stored.metrics_fetched_at == _NOW


async def test_run_returns_none_when_nothing_is_claimable() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    channel_publisher = FakeChannelPublisher()
    agent = _agent(uow_factory, channel_publisher, FakeClock(_NOW))

    result = await agent.run(tenant_id=new_tenant_id())

    assert result is None
    assert channel_publisher.metrics_calls == []
