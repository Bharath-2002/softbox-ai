from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.content_draft import ContentDraft
from app.features.content.reject_content_draft import RejectContentDraft
from app.shared.errors import NotFoundError
from app.shared.ids import (
    new_content_draft_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[RejectContentDraft, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return RejectContentDraft(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed_pending_approval(uow_factory: FakeUnitOfWorkFactory) -> tuple[object, ContentDraft]:
    tenant_id = new_tenant_id()
    draft = ContentDraft.create(
        tenant_id,
        new_product_variant_id(),
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
    return tenant_id, draft


async def test_rejecting_records_the_reason() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, draft = await _seed_pending_approval(uow_factory)
    rejecter = new_user_id()

    rejected = await use_case(
        tenant_id=tenant_id, draft_id=draft.id, reason="wrong tone", rejected_by=rejecter
    )

    assert rejected.status.value == "rejected"
    assert rejected.rejection_reason == "wrong tone"
    stored = await uow_factory.content_drafts.get(tenant_id, draft.id)
    assert stored is not None
    assert stored.rejection_reason == "wrong tone"


async def test_rejecting_writes_an_audit_log_entry() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, draft = await _seed_pending_approval(uow_factory)

    await use_case(
        tenant_id=tenant_id, draft_id=draft.id, reason="wrong tone", rejected_by=new_user_id()
    )

    entries = await uow_factory.audit_log.list_for_subject(tenant_id, "content_draft", draft.id)
    assert len(entries) == 1
    assert entries[0].action == "content_draft.rejected"


async def test_an_unknown_draft_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            draft_id=new_content_draft_id(),
            reason="x",
            rejected_by=new_user_id(),
        )
