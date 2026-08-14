"""Exercises the real ``StartContentDraftGeneration``/
``CompleteContentDraftGeneration``/``FailContentDraftGeneration`` use cases
wired together the way ``bootstrap/di.py`` will wire them - only
``TextGeneration`` is a fake. Proves the agent owns no transaction of its
own, the same property ``test_catalog_image_qc.py``/``test_generation_render.py``
prove for their own agents.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.agents.copywriting import CopywritingAgent
from app.entities.category import Category
from app.entities.product import Product
from app.entities.product_variant import ProductVariant
from app.entities.setting import Setting, SettingScope
from app.features.content.complete_content_draft_generation import (
    CompleteContentDraftGeneration,
)
from app.features.content.fail_content_draft_generation import FailContentDraftGeneration
from app.features.content.start_content_draft_generation import (
    JOB_TYPE,
    StartContentDraftGeneration,
)
from app.services.ports.text_generation import GeneratedCopy
from app.shared.ids import new_category_spec_version_id, new_tenant_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.text_generation import FakeTextGeneration
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_MODEL = "fake-text-model"


def _agent(
    uow_factory: FakeUnitOfWorkFactory, text_generation: FakeTextGeneration
) -> CopywritingAgent:
    clock = FakeClock(_NOW)
    return CopywritingAgent(
        StartContentDraftGeneration(uow_factory, clock),
        CompleteContentDraftGeneration(uow_factory, clock),
        FailContentDraftGeneration(uow_factory, clock),
        text_generation,
    )


async def _seed_variant(uow_factory: FakeUnitOfWorkFactory) -> tuple[object, object, object]:
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
        attributes={"colour": "red"},
        created_by=user_id,
        now=_NOW,
    )
    await uow_factory.products.add(product)
    variant = ProductVariant.create(
        tenant_id, product.id, axis_values={}, created_by=user_id, now=_NOW
    )
    await uow_factory.product_variants.add(variant)
    return tenant_id, variant.id, category.id


async def test_run_returns_none_when_nothing_is_claimable() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    agent = _agent(uow_factory, FakeTextGeneration())

    assert await agent.run(tenant_id=new_tenant_id()) is None


async def test_a_successful_generation_creates_a_content_draft() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    text_generation = FakeTextGeneration()
    agent = _agent(uow_factory, text_generation)
    tenant_id, variant_id, _category_id = await _seed_variant(uow_factory)
    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={
            "variant_id": str(variant_id),
            "channel": "instagram",
            "locale": "en",
            "model": _MODEL,
        },
        run_at=_NOW,
        now=_NOW,
    )

    draft = await agent.run(tenant_id=tenant_id)

    assert draft is not None
    assert draft.status.value == "generated"
    assert len(text_generation.calls) == 1


async def test_a_provider_failure_fails_the_job_and_returns_none() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    text_generation = FakeTextGeneration()
    text_generation.next_error = RuntimeError("provider unavailable")
    agent = _agent(uow_factory, text_generation)
    tenant_id, variant_id, _category_id = await _seed_variant(uow_factory)
    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={
            "variant_id": str(variant_id),
            "channel": "instagram",
            "locale": "en",
            "model": _MODEL,
        },
        run_at=_NOW,
        now=_NOW,
    )

    draft = await agent.run(tenant_id=tenant_id)

    assert draft is None
    listed = await uow_factory.content_drafts.list_for_variant(tenant_id, variant_id)
    assert listed == []


async def test_a_forbidden_claim_violation_fails_the_job_and_returns_none() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    text_generation = FakeTextGeneration()
    text_generation.next_result = GeneratedCopy(
        title="A saree that cures arthritis",
        body="Wear it daily.",
        hashtags=[],
        cta=None,
        alt_text="A saree.",
        model=_MODEL,
        cost_micros=0,
        latency_ms=0,
    )
    agent = _agent(uow_factory, text_generation)
    tenant_id, variant_id, category_id = await _seed_variant(uow_factory)
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
    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={
            "variant_id": str(variant_id),
            "channel": "instagram",
            "locale": "en",
            "model": _MODEL,
        },
        run_at=_NOW,
        now=_NOW,
    )

    draft = await agent.run(tenant_id=tenant_id)

    assert draft is None
    listed = await uow_factory.content_drafts.list_for_variant(tenant_id, variant_id)
    assert listed == []
