from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.product_variant import ProductVariant
from app.entities.publication import Publication, PublicationStatus
from app.entities.social_account import SocialAccount
from app.features.publishing.cancel_publication import CancelPublication
from app.shared.errors import NotFoundError, ValidationError
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
    return tenant_id, publication


async def test_cancelling_a_scheduled_publication_moves_to_cancelled_and_writes_audit_log() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed(uow_factory)
    use_case = CancelPublication(uow_factory, FakeClock(_NOW))
    actor = new_user_id()

    result = await use_case(tenant_id=tenant_id, publication_id=publication.id, cancelled_by=actor)

    assert result.status is PublicationStatus.CANCELLED
    stored = await uow_factory.publications.get(tenant_id, publication.id)
    assert stored is not None
    assert stored.status is PublicationStatus.CANCELLED
    entries = await uow_factory.audit_log.list_for_subject(
        tenant_id, subject_type="publication", subject_id=publication.id
    )
    assert len(entries) == 1
    assert entries[0].action == "publication.cancelled"
    assert entries[0].actor_user_id == actor


async def test_cannot_cancel_once_dispatching() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed(uow_factory)
    publication.mark_dispatching(now=_NOW)
    await uow_factory.publications.update(publication)
    use_case = CancelPublication(uow_factory, FakeClock(_NOW))

    with pytest.raises(ValidationError):
        await use_case(
            tenant_id=tenant_id, publication_id=publication.id, cancelled_by=new_user_id()
        )


async def test_an_unknown_publication_is_not_found() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    use_case = CancelPublication(uow_factory, FakeClock(_NOW))

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            publication_id=PublicationId(new_publication_id()),
            cancelled_by=new_user_id(),
        )
