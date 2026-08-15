from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.entities.product_variant import ProductVariant
from app.entities.publication import Publication, PublicationStatus
from app.entities.social_account import SocialAccount
from app.features.publishing.release_scheduled_publications import (
    ReleaseScheduledPublicationsForTenant,
)
from app.features.publishing.start_publication_publish import JOB_TYPE
from app.shared.ids import new_product_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case(
    uow_factory: FakeUnitOfWorkFactory, clock: FakeClock
) -> ReleaseScheduledPublicationsForTenant:
    return ReleaseScheduledPublicationsForTenant(uow_factory, clock)


async def _seed_scheduled_publication(
    uow_factory: FakeUnitOfWorkFactory, *, due_at: datetime
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
        due_at=due_at,
        now=_NOW,
    )
    await uow_factory.publications.add(publication)
    return tenant_id, publication


async def test_a_due_scheduled_publication_is_released_and_enqueued() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed_scheduled_publication(
        uow_factory, due_at=_NOW + timedelta(hours=1)
    )
    clock = FakeClock(_NOW + timedelta(hours=1))
    use_case = _use_case(uow_factory, clock)

    released = await use_case(tenant_id)

    assert released == 1
    stored = await uow_factory.publications.get(tenant_id, publication.id)
    assert stored is not None
    # status is unchanged - the poller only pushes `due_at` forward as a
    # duplicate-enqueue guard; `StartPublicationPublish` is what actually
    # transitions the row to `dispatching` once the job is claimed
    assert stored.status is PublicationStatus.SCHEDULED
    assert stored.due_at > clock.now()
    job = await uow_factory.task_queue.claim(
        tenant_id, claimed_by="test", job_type=JOB_TYPE, now=clock.now()
    )
    assert job is not None
    assert job.payload == {"publication_id": str(publication.id)}


async def test_a_not_yet_due_scheduled_publication_is_left_alone() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed_scheduled_publication(
        uow_factory, due_at=_NOW + timedelta(days=1)
    )
    use_case = _use_case(uow_factory, FakeClock(_NOW))

    released = await use_case(tenant_id)

    assert released == 0
    stored = await uow_factory.publications.get(tenant_id, publication.id)
    assert stored is not None
    assert stored.status is PublicationStatus.SCHEDULED
    assert stored.due_at == _NOW + timedelta(days=1)  # untouched
    job = await uow_factory.task_queue.claim(
        tenant_id, claimed_by="test", job_type=JOB_TYPE, now=_NOW
    )
    assert job is None


async def test_two_sweeps_do_not_double_enqueue_the_same_row() -> None:
    """The `_DISPATCH_GRACE` push is what makes this safe without a
    status transition: a second sweep immediately after the first must
    not see the row as due again."""
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, _publication = await _seed_scheduled_publication(
        uow_factory, due_at=_NOW + timedelta(hours=1)
    )
    clock = FakeClock(_NOW + timedelta(hours=1))
    use_case = _use_case(uow_factory, clock)

    first_pass = await use_case(tenant_id)
    second_pass = await use_case(tenant_id)

    assert first_pass == 1
    assert second_pass == 0


async def test_returns_zero_when_nothing_is_due() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = _use_case(uow_factory, FakeClock(_NOW))

    released = await use_case(new_tenant_id())

    assert released == 0
