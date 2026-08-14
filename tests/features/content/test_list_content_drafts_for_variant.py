from __future__ import annotations

from datetime import UTC, datetime

from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.content_draft import ContentDraft, ContentDraftId
from app.features.content.list_content_drafts_for_variant import ListContentDraftsForVariant
from app.shared.ids import new_content_draft_id, new_product_variant_id, new_tenant_id

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[ListContentDraftsForVariant, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return ListContentDraftsForVariant(uow_factory), uow_factory


def _draft(tenant_id: object, variant_id: object, *, channel: str = "instagram") -> ContentDraft:
    return ContentDraft.create(
        tenant_id,
        variant_id,
        channel=channel,
        locale="en",
        body="Crafted with care.",
        alt_text="A folded saree.",
        model="fake-text-model",
        prompt_version="v1",
        now=_NOW,
    )


async def test_lists_live_drafts_for_the_variant() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    variant_id = new_product_variant_id()
    draft = _draft(tenant_id, variant_id)
    await uow_factory.content_drafts.add(draft)

    listed = await use_case(tenant_id=tenant_id, variant_id=variant_id)

    assert [d.id for d in listed] == [draft.id]


async def test_excludes_superseded_drafts() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    variant_id = new_product_variant_id()
    draft = _draft(tenant_id, variant_id)
    await uow_factory.content_drafts.add(draft)
    draft.mark_superseded(by=ContentDraftId(new_content_draft_id()), now=_NOW)
    await uow_factory.content_drafts.update(draft)

    listed = await use_case(tenant_id=tenant_id, variant_id=variant_id)

    assert listed == []


async def test_excludes_drafts_for_a_different_variant() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    variant_id = new_product_variant_id()
    other_variant_id = new_product_variant_id()
    await uow_factory.content_drafts.add(_draft(tenant_id, other_variant_id))

    listed = await use_case(tenant_id=tenant_id, variant_id=variant_id)

    assert listed == []
