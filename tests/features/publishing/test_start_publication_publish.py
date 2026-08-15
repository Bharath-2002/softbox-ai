from __future__ import annotations

from datetime import UTC, datetime

from app.entities.product_variant import ProductVariant
from app.entities.publication import Publication
from app.entities.social_account import SocialAccount
from app.features.publishing.start_publication_publish import JOB_TYPE, StartPublicationPublish
from app.shared.ids import new_product_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def _seed(uow_factory: FakeUnitOfWorkFactory) -> tuple[object, Publication]:
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
    await uow_factory.publications.add(publication)
    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={"publication_id": str(publication.id)},
        run_at=_NOW,
        now=_NOW,
    )
    return tenant_id, publication


async def test_claiming_a_job_for_a_cancelled_publication_dead_letters_instead_of_raising() -> None:
    """The race an advisor pass caught: the `due_at` poller can enqueue a
    job for a `SCHEDULED` row, and `CancelPublication` (which only
    requires `SCHEDULED`) can land before `StartPublicationPublish` claims
    it. `mark_dispatching()` would raise on a `CANCELLED` row - this must
    not propagate uncaught out of the worker step."""
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed(uow_factory)
    publication.cancel(now=_NOW)
    await uow_factory.publications.update(publication)
    use_case = StartPublicationPublish(uow_factory, FakeClock(_NOW))

    result = await use_case(tenant_id=tenant_id)

    assert result is None
    stored = await uow_factory.publications.get(tenant_id, publication.id)
    assert stored is not None
    assert stored.status.value == "cancelled"  # untouched


async def test_claiming_a_job_for_a_normal_scheduled_publication_succeeds() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed(uow_factory)
    use_case = StartPublicationPublish(uow_factory, FakeClock(_NOW))

    result = await use_case(tenant_id=tenant_id)

    assert result is not None
    assert result.publication_id == publication.id
