from __future__ import annotations

import pytest

from app.entities.content_draft import ContentDraft, ContentDraftId, ContentDraftStatus
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import (
    new_content_draft_id,
    new_product_variant_id,
    new_tenant_id,
    new_user_id,
)


def _draft() -> ContentDraft:
    return ContentDraft.create(
        new_tenant_id(),
        new_product_variant_id(),
        channel="instagram",
        locale="en",
        body="Crafted with care.",
        alt_text="A folded saree.",
        model="fake-text-model",
        prompt_version="v1",
        now=utcnow(),
    )


def test_a_new_draft_starts_generated() -> None:
    draft = _draft()

    assert draft.status == ContentDraftStatus.GENERATED
    assert draft.rejection_reason is None
    assert draft.superseded_by is None


def test_moves_to_pending_approval() -> None:
    draft = _draft()

    draft.mark_pending_approval(now=utcnow())

    assert draft.status == ContentDraftStatus.PENDING_APPROVAL


def test_a_generated_draft_cannot_be_approved_directly() -> None:
    draft = _draft()

    with pytest.raises(ValidationError):
        draft.approve(approved_by=None, now=utcnow())


def test_a_generated_draft_cannot_be_rejected_directly() -> None:
    draft = _draft()

    with pytest.raises(ValidationError):
        draft.reject(reason="not good enough", now=utcnow())


def test_a_pending_approval_draft_can_be_approved_by_a_human() -> None:
    draft = _draft()
    draft.mark_pending_approval(now=utcnow())
    approver = new_user_id()

    draft.approve(approved_by=approver, now=utcnow())

    assert draft.status == ContentDraftStatus.APPROVED


def test_a_pending_approval_draft_can_be_rejected_with_a_reason() -> None:
    draft = _draft()
    draft.mark_pending_approval(now=utcnow())

    draft.reject(reason="wrong tone for this channel", now=utcnow())

    assert draft.status == ContentDraftStatus.REJECTED
    assert draft.rejection_reason == "wrong tone for this channel"


def test_an_approved_draft_cannot_be_approved_again() -> None:
    draft = _draft()
    draft.mark_pending_approval(now=utcnow())
    draft.approve(approved_by=None, now=utcnow())

    with pytest.raises(ValidationError):
        draft.approve(approved_by=None, now=utcnow())


def test_a_generated_draft_cannot_move_to_pending_approval_twice() -> None:
    draft = _draft()
    draft.mark_pending_approval(now=utcnow())

    with pytest.raises(ValidationError):
        draft.mark_pending_approval(now=utcnow())


def test_an_already_superseded_draft_cannot_be_superseded_again() -> None:
    draft = _draft()
    draft.mark_superseded(by=ContentDraftId(new_content_draft_id()), now=utcnow())

    with pytest.raises(ValidationError):
        draft.mark_superseded(by=ContentDraftId(new_content_draft_id()), now=utcnow())
