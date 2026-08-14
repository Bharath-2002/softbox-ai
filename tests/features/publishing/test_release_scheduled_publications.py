from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.entities.product_variant import ProductVariant
from app.entities.publication import Publication, PublicationStatus
from app.entities.social_account import SocialAccount
from app.features.publishing.release_scheduled_publications import (
    ReleaseScheduledPublicationsForTenant,
)
from app.shared.ids import new_product_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case(
    uow_factory: FakeUnitOfWorkFactory, clock: FakeClock
) -> ReleaseScheduledPublicationsForTenant:
    return ReleaseScheduledPublicationsForTenant(uow_factory, clock)


async def _seed_scheduled_publication(
    uow_factory: FakeUnitOfWorkFactory, *, scheduled_at: datetime
) -> tuple[object, Publication]:
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
        scheduled_at=scheduled_at,
        now=_NOW,
    )
    await uow_factory.publications.add(publication)
    return tenant_id, publication


async def test_a_due_scheduled_publication_is_released_and_enqueued() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed_scheduled_publication(
        uow_factory, scheduled_at=_NOW + timedelta(hours=1)
    )
    clock = FakeClock(_NOW + timedelta(hours=1))
    use_case = _use_case(uow_factory, clock)

    released = await use_case(tenant_id)

    assert released == 1
    stored = await uow_factory.publications.get(tenant_id, publication.id)
    assert stored is not None
    assert stored.status is PublicationStatus.PENDING
    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert len(events) == 1
    assert events[0].event_type == "publication.publish_requested"
    assert events[0].payload == {"publication_id": str(publication.id)}


async def test_a_not_yet_due_scheduled_publication_is_left_alone() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed_scheduled_publication(
        uow_factory, scheduled_at=_NOW + timedelta(days=1)
    )
    use_case = _use_case(uow_factory, FakeClock(_NOW))

    released = await use_case(tenant_id)

    assert released == 0
    stored = await uow_factory.publications.get(tenant_id, publication.id)
    assert stored is not None
    assert stored.status is PublicationStatus.SCHEDULED
    events = await uow_factory.outbox_events.list_unpublished(tenant_id, limit=10)
    assert events == []


async def test_returns_zero_when_nothing_is_due() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = _use_case(uow_factory, FakeClock(_NOW))

    released = await use_case(new_tenant_id())

    assert released == 0
