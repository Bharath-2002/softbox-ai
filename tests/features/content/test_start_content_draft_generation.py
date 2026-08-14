from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

from app.entities.category import Category
from app.entities.product import Product
from app.entities.product_variant import ProductVariant
from app.entities.setting import Setting, SettingScope
from app.features.content.start_content_draft_generation import (
    JOB_TYPE,
    StartContentDraftGeneration,
)
from app.shared.ids import (
    CategoryId,
    ProductVariantId,
    TenantId,
    new_category_spec_version_id,
    new_tenant_id,
    new_user_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_MODEL = "fake-text-model"


def _use_case() -> tuple[StartContentDraftGeneration, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return StartContentDraftGeneration(uow_factory, FakeClock(_NOW)), uow_factory


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
        attributes={"colour": "red"},
        created_by=user_id,
        now=_NOW,
    )
    await uow_factory.products.add(product)
    variant = ProductVariant.create(
        tenant_id,
        product.id,
        axis_values={},
        attributes={"size": "free"},
        created_by=user_id,
        now=_NOW,
    )
    await uow_factory.product_variants.add(variant)
    return tenant_id, variant.id, category.id


async def _enqueue(
    uow_factory: FakeUnitOfWorkFactory, tenant_id: TenantId, variant_id: ProductVariantId
) -> UUID:
    return await uow_factory.task_queue.enqueue(
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


async def test_returns_none_when_nothing_is_claimable() -> None:
    use_case, _uow_factory = _use_case()

    assert await use_case(tenant_id=new_tenant_id()) is None


async def test_claims_the_job_and_composes_a_prompt() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, _category_id = await _seed_variant(uow_factory)
    await _enqueue(uow_factory, tenant_id, variant_id)

    ctx = await use_case(tenant_id=tenant_id)

    assert ctx is not None
    assert ctx.variant_id == variant_id
    assert ctx.channel == "instagram"
    assert ctx.locale == "en"
    assert ctx.model == _MODEL
    assert ctx.forbidden_claims == []
    assert "colour: red" in ctx.prompt
    assert "size: free" in ctx.prompt


async def test_an_unset_forbidden_claims_setting_resolves_to_an_empty_list() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, _category_id = await _seed_variant(uow_factory)
    await _enqueue(uow_factory, tenant_id, variant_id)

    ctx = await use_case(tenant_id=tenant_id)

    assert ctx is not None
    assert ctx.forbidden_claims == []


async def test_a_configured_forbidden_claims_list_is_resolved() -> None:
    use_case, uow_factory = _use_case()
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
    await _enqueue(uow_factory, tenant_id, variant_id)

    ctx = await use_case(tenant_id=tenant_id)

    assert ctx is not None
    assert ctx.forbidden_claims == ["cures arthritis"]


async def test_a_non_list_forbidden_claims_value_fails_the_job() -> None:
    use_case, uow_factory = _use_case()
    tenant_id, variant_id, category_id = await _seed_variant(uow_factory)
    await uow_factory.settings.add(
        Setting.create(
            scope_type=SettingScope.CATEGORY,
            tenant_id=tenant_id,
            scope_id=category_id,
            key="content.forbidden_claims",
            value="no medical claims",
            now=_NOW,
        )
    )
    job_id = await _enqueue(uow_factory, tenant_id, variant_id)

    ctx = await use_case(tenant_id=tenant_id)

    assert ctx is None
    job = await uow_factory.task_queue.get(tenant_id, job_id)
    assert job is not None
    assert job.status == "pending"  # retried, not dead - one attempt is below max_attempts
    assert job.last_error is not None
    assert "content.forbidden_claims" in job.last_error
