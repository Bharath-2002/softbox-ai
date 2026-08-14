"""An in-memory ``UnitOfWork`` for use-case tests.

Unlike the SQL contract tests, this fake's job is not to prove transactional
correctness against real Postgres (``test_tenant_isolation.py`` already does
that) — it exists so a use case's own logic (which repository gets called,
with what, in what order, how it reacts to what comes back) can be tested
fast and deterministically. ``committed`` / ``rolled_back`` let a test assert
the use case actually exited its unit of work the way it meant to.
"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType

from app.shared.ids import TenantId
from tests.fakes.asset_repository import InMemoryAssetRepository
from tests.fakes.attribute_definition_repository import InMemoryAttributeDefinitionRepository
from tests.fakes.audit_log_repository import InMemoryAuditLogRepository
from tests.fakes.catalog_image_repository import InMemoryCatalogImageRepository
from tests.fakes.catalog_image_slot_repository import InMemoryCatalogImageSlotRepository
from tests.fakes.catalog_slot_input_requirement_repository import (
    InMemoryCatalogSlotInputRequirementRepository,
)
from tests.fakes.catalog_template_repository import InMemoryCatalogTemplateRepository
from tests.fakes.category_repository import InMemoryCategoryRepository
from tests.fakes.category_spec_version_repository import InMemoryCategorySpecVersionRepository
from tests.fakes.content_draft_repository import InMemoryContentDraftRepository
from tests.fakes.generation_item_repository import InMemoryGenerationItemRepository
from tests.fakes.generation_request_repository import InMemoryGenerationRequestRepository
from tests.fakes.idempotency_repository import InMemoryIdempotencyRepository
from tests.fakes.identity_repository import InMemoryIdentityRepository
from tests.fakes.input_image_slot_repository import InMemoryInputImageSlotRepository
from tests.fakes.outbox_event_repository import InMemoryOutboxEventRepository
from tests.fakes.platform_admin_repository import InMemoryPlatformAdminRepository
from tests.fakes.product_input_image_repository import InMemoryProductInputImageRepository
from tests.fakes.product_repository import InMemoryProductRepository
from tests.fakes.product_variant_repository import InMemoryProductVariantRepository
from tests.fakes.quota_reservation_repository import InMemoryQuotaReservationRepository
from tests.fakes.session_repository import InMemorySessionRepository
from tests.fakes.settings_repository import InMemorySettingsRepository
from tests.fakes.social_account_repository import InMemorySocialAccountRepository
from tests.fakes.task_queue import InMemoryTaskQueue
from tests.fakes.tenant_membership_repository import InMemoryTenantMembershipRepository
from tests.fakes.tenant_repository import InMemoryTenantRepository
from tests.fakes.user_repository import InMemoryUserRepository
from tests.fakes.variant_axis_repository import InMemoryVariantAxisRepository
from tests.fakes.variant_axis_value_repository import InMemoryVariantAxisValueRepository


class FakeUnitOfWork:
    def __init__(
        self,
        *,
        users: InMemoryUserRepository,
        identities: InMemoryIdentityRepository,
        platform_admins: InMemoryPlatformAdminRepository,
        tenant_memberships: InMemoryTenantMembershipRepository,
        sessions: InMemorySessionRepository,
        idempotency_keys: InMemoryIdempotencyRepository,
        audit_log: InMemoryAuditLogRepository,
        categories: InMemoryCategoryRepository,
        attribute_definitions: InMemoryAttributeDefinitionRepository,
        variant_axes: InMemoryVariantAxisRepository,
        variant_axis_values: InMemoryVariantAxisValueRepository,
        input_image_slots: InMemoryInputImageSlotRepository,
        catalog_image_slots: InMemoryCatalogImageSlotRepository,
        catalog_slot_input_requirements: InMemoryCatalogSlotInputRequirementRepository,
        category_spec_versions: InMemoryCategorySpecVersionRepository,
        settings: InMemorySettingsRepository,
        assets: InMemoryAssetRepository,
        catalog_templates: InMemoryCatalogTemplateRepository,
        products: InMemoryProductRepository,
        product_variants: InMemoryProductVariantRepository,
        product_input_images: InMemoryProductInputImageRepository,
        outbox_events: InMemoryOutboxEventRepository,
        task_queue: InMemoryTaskQueue,
        tenants: InMemoryTenantRepository,
        quota_reservations: InMemoryQuotaReservationRepository,
        generation_requests: InMemoryGenerationRequestRepository,
        generation_items: InMemoryGenerationItemRepository,
        catalog_images: InMemoryCatalogImageRepository,
        content_drafts: InMemoryContentDraftRepository,
        social_accounts: InMemorySocialAccountRepository,
        tenant_id: TenantId | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.users = users
        self.identities = identities
        self.platform_admins = platform_admins
        self.tenant_memberships = tenant_memberships
        self.sessions = sessions
        self.idempotency_keys = idempotency_keys
        self.audit_log = audit_log
        self.categories = categories
        self.attribute_definitions = attribute_definitions
        self.variant_axes = variant_axes
        self.variant_axis_values = variant_axis_values
        self.input_image_slots = input_image_slots
        self.catalog_image_slots = catalog_image_slots
        self.catalog_slot_input_requirements = catalog_slot_input_requirements
        self.category_spec_versions = category_spec_versions
        self.settings = settings
        self.assets = assets
        self.catalog_templates = catalog_templates
        self.products = products
        self.product_variants = product_variants
        self.product_input_images = product_input_images
        self.outbox_events = outbox_events
        self.task_queue = task_queue
        self.tenants = tenants
        self.quota_reservations = quota_reservations
        self.generation_requests = generation_requests
        self.generation_items = generation_items
        self.catalog_images = catalog_images
        self.content_drafts = content_drafts
        self.social_accounts = social_accounts
        self.committed = False
        self.rolled_back = False

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is None:
            self.committed = True
        else:
            self.rolled_back = True


class FakeUnitOfWorkFactory:
    """Repositories are shared across every unit of work this factory hands
    out, so state persists between calls within one test — the same thing a
    real database gives a use case that opens several transactions in
    sequence (login, then a later refresh)."""

    def __init__(self) -> None:
        self.users = InMemoryUserRepository()
        self.identities = InMemoryIdentityRepository()
        self.platform_admins = InMemoryPlatformAdminRepository()
        self.tenant_memberships = InMemoryTenantMembershipRepository()
        self.sessions = InMemorySessionRepository()
        self.idempotency_keys = InMemoryIdempotencyRepository()
        self.audit_log = InMemoryAuditLogRepository()
        self.categories = InMemoryCategoryRepository()
        self.attribute_definitions = InMemoryAttributeDefinitionRepository()
        self.variant_axes = InMemoryVariantAxisRepository()
        self.variant_axis_values = InMemoryVariantAxisValueRepository()
        self.input_image_slots = InMemoryInputImageSlotRepository()
        self.catalog_image_slots = InMemoryCatalogImageSlotRepository()
        self.catalog_slot_input_requirements = InMemoryCatalogSlotInputRequirementRepository()
        self.category_spec_versions = InMemoryCategorySpecVersionRepository()
        self.settings = InMemorySettingsRepository()
        self.assets = InMemoryAssetRepository()
        self.catalog_templates = InMemoryCatalogTemplateRepository()
        self.products = InMemoryProductRepository()
        self.product_variants = InMemoryProductVariantRepository()
        self.product_input_images = InMemoryProductInputImageRepository()
        self.outbox_events = InMemoryOutboxEventRepository()
        self.task_queue = InMemoryTaskQueue()
        self.tenants = InMemoryTenantRepository()
        self.quota_reservations = InMemoryQuotaReservationRepository()
        self.generation_requests = InMemoryGenerationRequestRepository()
        self.generation_items = InMemoryGenerationItemRepository()
        self.catalog_images = InMemoryCatalogImageRepository(self.product_variants)
        self.content_drafts = InMemoryContentDraftRepository()
        self.social_accounts = InMemorySocialAccountRepository()

    def __call__(self, tenant_id: TenantId | None = None) -> FakeUnitOfWork:
        return FakeUnitOfWork(
            users=self.users,
            identities=self.identities,
            platform_admins=self.platform_admins,
            tenant_memberships=self.tenant_memberships,
            sessions=self.sessions,
            idempotency_keys=self.idempotency_keys,
            audit_log=self.audit_log,
            categories=self.categories,
            attribute_definitions=self.attribute_definitions,
            variant_axes=self.variant_axes,
            variant_axis_values=self.variant_axis_values,
            input_image_slots=self.input_image_slots,
            catalog_image_slots=self.catalog_image_slots,
            catalog_slot_input_requirements=self.catalog_slot_input_requirements,
            category_spec_versions=self.category_spec_versions,
            settings=self.settings,
            assets=self.assets,
            catalog_templates=self.catalog_templates,
            products=self.products,
            product_variants=self.product_variants,
            product_input_images=self.product_input_images,
            outbox_events=self.outbox_events,
            task_queue=self.task_queue,
            tenants=self.tenants,
            quota_reservations=self.quota_reservations,
            generation_requests=self.generation_requests,
            generation_items=self.generation_items,
            catalog_images=self.catalog_images,
            content_drafts=self.content_drafts,
            social_accounts=self.social_accounts,
            tenant_id=tenant_id,
        )


def fake_unit_of_work_factory() -> Callable[[TenantId | None], FakeUnitOfWork]:
    return FakeUnitOfWorkFactory()
