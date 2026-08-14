from __future__ import annotations

from datetime import UTC, datetime

from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.features.content.complete_content_draft_generation import (
    CompleteContentDraftGeneration,
)
from app.services.ports.text_generation import GeneratedCopy
from app.shared.ids import new_product_variant_id, new_tenant_id

_NOW = datetime(2026, 1, 1, tzinfo=UTC)

_COPY = GeneratedCopy(
    title="A handwoven classic",
    body="Crafted with care.",
    hashtags=["#saree"],
    cta="Shop now",
    alt_text="A folded saree.",
    model="fake-text-model",
    cost_micros=0,
    latency_ms=0,
)


def _use_case() -> tuple[CompleteContentDraftGeneration, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return CompleteContentDraftGeneration(uow_factory, FakeClock(_NOW)), uow_factory


async def _job_id(uow_factory: FakeUnitOfWorkFactory, tenant_id: object) -> object:
    return await uow_factory.task_queue.enqueue(
        tenant_id, job_type="content_draft.generate_requested", payload={}, run_at=_NOW, now=_NOW
    )


async def test_clean_copy_creates_a_content_draft_and_completes_the_job() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    variant_id = new_product_variant_id()
    job_id = await _job_id(uow_factory, tenant_id)

    draft = await use_case(
        tenant_id=tenant_id,
        variant_id=variant_id,
        channel="instagram",
        locale="en",
        job_id=job_id,
        copy=_COPY,
        forbidden_claims=[],
    )

    assert draft is not None
    assert draft.status.value == "generated"
    assert draft.body == "Crafted with care."
    stored = await uow_factory.content_drafts.get(tenant_id, draft.id)
    assert stored is not None
    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "succeeded"
    entries = await uow_factory.audit_log.list_for_subject(tenant_id, "content_draft", draft.id)
    assert len(entries) == 1


async def test_a_forbidden_claim_fails_the_job_and_writes_no_draft() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    variant_id = new_product_variant_id()
    job_id = await _job_id(uow_factory, tenant_id)

    draft = await use_case(
        tenant_id=tenant_id,
        variant_id=variant_id,
        channel="instagram",
        locale="en",
        job_id=job_id,
        copy=_COPY,
        forbidden_claims=["crafted with care"],
    )

    assert draft is None
    listed = await uow_factory.content_drafts.list_for_variant(tenant_id, variant_id)
    assert listed == []
    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "pending"  # retried, not dead - one attempt is below max_attempts
    assert job.last_error is not None
    assert "crafted with care" in job.last_error


async def test_regenerating_supersedes_the_existing_live_draft() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    variant_id = new_product_variant_id()
    first_job_id = await _job_id(uow_factory, tenant_id)
    first = await use_case(
        tenant_id=tenant_id,
        variant_id=variant_id,
        channel="instagram",
        locale="en",
        job_id=first_job_id,
        copy=_COPY,
        forbidden_claims=[],
    )
    assert first is not None

    second_job_id = await _job_id(uow_factory, tenant_id)
    second = await use_case(
        tenant_id=tenant_id,
        variant_id=variant_id,
        channel="instagram",
        locale="en",
        job_id=second_job_id,
        copy=_COPY,
        forbidden_claims=[],
    )
    assert second is not None
    assert second.id != first.id

    old = await uow_factory.content_drafts.get(tenant_id, first.id)
    assert old is not None
    assert old.superseded_by == second.id
    live = await uow_factory.content_drafts.get_live(
        tenant_id, variant_id, channel="instagram", locale="en"
    )
    assert live is not None
    assert live.id == second.id
