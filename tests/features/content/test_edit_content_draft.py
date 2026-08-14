from __future__ import annotations

from datetime import UTC, datetime

import pytest
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.category import Category
from app.entities.content_draft import ContentDraft
from app.entities.product import Product
from app.entities.product_variant import ProductVariant
from app.entities.setting import Setting, SettingScope
from app.features.content.edit_content_draft import EditContentDraft
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import (
    CategoryId,
    ContentDraftId,
    ProductVariantId,
    TenantId,
    new_category_spec_version_id,
    new_content_draft_id,
    new_tenant_id,
    new_user_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[EditContentDraft, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return EditContentDraft(uow_factory, FakeClock(_NOW)), uow_factory


async def _seed_variant(
    uow_factory: FakeUnitOfWorkFactory,
) -> tuple[TenantId, ProductVariantId, CategoryId]:
    tenant_id = new_tenant_id()
    user_id = new_user_id()
    category = Category.create(
        tenant_id, key="sarees", name="Sarees", slug="sarees", parent=None, now=_NOW
    )
    await uow_factory.categories.add(category)
    product = Product.create(
        tenant_id,
        category.id,
        new_category_spec_version_id(),
        attributes={},
        created_by=user_id,
        now=_NOW,
    )
    await uow_factory.products.add(product)
    variant = ProductVariant.create(
        tenant_id, product.id, axis_values={}, created_by=user_id, now=_NOW
    )
    await uow_factory.product_variants.add(variant)
    return tenant_id, variant.id, category.id


async def _seed_pending_approval_draft(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: TenantId, variant_id: ProductVariantId
) -> ContentDraft:
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
    draft.mark_pending_approval(now=_NOW)
    await uow_factory.content_drafts.add(draft)
    return draft


async def test_editing_supersedes_the_live_draft_and_creates_a_pending_approval_replacement() -> (
    None
):
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, _category_id = await _seed_variant(uow_factory)
    original = await _seed_pending_approval_draft(uow_factory, tenant_id, variant_id)
    editor = new_user_id()

    edited = await use_case(
        tenant_id=tenant_id,
        draft_id=original.id,
        edited_by=editor,
        title="A rewritten title",
        body="Hand-edited copy.",
        hashtags=["#handloom"],
        cta="Buy now",
        alt_text="A folded saree, edited.",
    )

    assert edited.id != original.id
    assert edited.body == "Hand-edited copy."
    assert edited.status.value == "pending_approval"
    assert edited.edited_by == editor
    assert edited.model == original.model
    assert edited.prompt_version == original.prompt_version
    stored_original = await uow_factory.content_drafts.get(tenant_id, original.id)
    assert stored_original is not None
    assert stored_original.superseded_by == edited.id
    live = await uow_factory.content_drafts.get_live(
        tenant_id, variant_id, channel="instagram", locale="en"
    )
    assert live is not None
    assert live.id == edited.id


async def test_editing_writes_an_audit_log_entry() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, _category_id = await _seed_variant(uow_factory)
    original = await _seed_pending_approval_draft(uow_factory, tenant_id, variant_id)
    editor = new_user_id()

    edited = await use_case(
        tenant_id=tenant_id,
        draft_id=original.id,
        edited_by=editor,
        title=None,
        body="Hand-edited copy.",
        hashtags=[],
        cta=None,
        alt_text="A folded saree.",
    )

    entries = await uow_factory.audit_log.list_for_subject(tenant_id, "content_draft", edited.id)
    assert len(entries) == 1
    assert entries[0].action == "content_draft.edited"
    assert entries[0].actor_user_id == editor


async def test_auto_approves_when_approval_is_disabled_for_the_category() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, category_id = await _seed_variant(uow_factory)
    original = await _seed_pending_approval_draft(uow_factory, tenant_id, variant_id)
    await uow_factory.settings.add(
        Setting.create(
            scope_type=SettingScope.CATEGORY,
            tenant_id=tenant_id,
            scope_id=category_id,
            key="approval.required",
            value=False,
            now=_NOW,
        )
    )

    edited = await use_case(
        tenant_id=tenant_id,
        draft_id=original.id,
        edited_by=new_user_id(),
        title=None,
        body="Hand-edited copy.",
        hashtags=[],
        cta=None,
        alt_text="A folded saree.",
    )

    assert edited.status.value == "approved"


async def test_a_forbidden_claim_in_the_edit_raises_and_writes_no_row() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, category_id = await _seed_variant(uow_factory)
    original = await _seed_pending_approval_draft(uow_factory, tenant_id, variant_id)
    await uow_factory.settings.add(
        Setting.create(
            scope_type=SettingScope.CATEGORY,
            tenant_id=tenant_id,
            scope_id=category_id,
            key="content.forbidden_claims",
            value=["cures arthritis"],
            now=_NOW,
        )
    )

    with pytest.raises(ValidationError):
        await use_case(
            tenant_id=tenant_id,
            draft_id=original.id,
            edited_by=new_user_id(),
            title=None,
            body="This saree cures arthritis.",
            hashtags=[],
            cta=None,
            alt_text="A folded saree.",
        )

    listed = await uow_factory.content_drafts.list_for_variant(tenant_id, variant_id)
    assert len(listed) == 1
    assert listed[0].id == original.id
    assert listed[0].superseded_by is None


async def test_an_unknown_draft_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(
            tenant_id=new_tenant_id(),
            draft_id=ContentDraftId(new_content_draft_id()),
            edited_by=new_user_id(),
            title=None,
            body="x",
            hashtags=[],
            cta=None,
            alt_text="x",
        )


async def test_editing_an_already_superseded_draft_raises() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, _category_id = await _seed_variant(uow_factory)
    original = await _seed_pending_approval_draft(uow_factory, tenant_id, variant_id)
    original.mark_superseded(by=ContentDraftId(new_content_draft_id()), now=_NOW)
    await uow_factory.content_drafts.update(original)

    with pytest.raises(ValidationError):
        await use_case(
            tenant_id=tenant_id,
            draft_id=original.id,
            edited_by=new_user_id(),
            title=None,
            body="x",
            hashtags=[],
            cta=None,
            alt_text="x",
        )
