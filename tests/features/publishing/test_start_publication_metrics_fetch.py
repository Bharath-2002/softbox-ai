from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.entities.product_variant import ProductVariant
from app.entities.publication import Publication
from app.entities.social_account import SocialAccount
from app.features.publishing.start_publication_metrics_fetch import (
    StartPublicationMetricsFetch,
)
from app.shared.ids import new_product_id, new_tenant_id, new_user_id
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


async def test_claims_a_published_row_and_bumps_metrics_fetched_at() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed_published(uow_factory)
    use_case = StartPublicationMetricsFetch(uow_factory, FakeClock(_NOW))

    ctx = await use_case(tenant_id)

    assert ctx is not None
    assert ctx.publication_id == publication.id
    assert ctx.external_post_id == "post-1"
    stored = await uow_factory.publications.get(tenant_id, publication.id)
    assert stored is not None
    assert stored.metrics_fetched_at == _NOW


async def test_returns_none_when_nothing_is_claimable() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = StartPublicationMetricsFetch(uow_factory, FakeClock(_NOW))

    ctx = await use_case(new_tenant_id())

    assert ctx is None


async def test_does_not_reclaim_a_row_fetched_within_the_staleness_window() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, _publication = await _seed_published(uow_factory)
    use_case = StartPublicationMetricsFetch(uow_factory, FakeClock(_NOW))
    first = await use_case(tenant_id)
    assert first is not None

    clock = FakeClock(_NOW + timedelta(minutes=30))
    use_case_again = StartPublicationMetricsFetch(uow_factory, clock)
    second = await use_case_again(tenant_id, staleness=timedelta(hours=1))

    assert second is None
