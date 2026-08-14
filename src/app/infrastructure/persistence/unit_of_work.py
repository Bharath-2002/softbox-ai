"""The SQL implementation of the ``UnitOfWork`` port.

The one thing this module exists for: **``SET LOCAL`` the tenant, inside the
transaction, before any tenant-scoped statement runs (D3).**

Two details that are easy to get wrong and would silently defeat isolation:

- ``SET LOCAL app.current_tenant = 'xxx'`` cannot be parameterised — Postgres
  does not accept placeholders inside a bare ``SET`` statement. The
  parameterisable equivalent is ``select set_config(name, value, is_local)``,
  which is what this module uses.
- When no tenant is bound, ``current_setting(..., true)`` reads back as NULL
  on a connection that has never touched the GUC, or as an empty string on
  one that set it in an earlier transaction (Postgres, not this code — see
  ``migrations/rls.py``). Every RLS policy predicate normalises both with
  ``NULLIF(..., '')`` before comparing, so an unset tenant context reads as
  zero rows either way rather than a database error on a reused pooled
  connection.
"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.persistence.asset_repository import SqlAssetRepository
from app.infrastructure.persistence.attribute_definition_repository import (
    SqlAttributeDefinitionRepository,
)
from app.infrastructure.persistence.audit_log_repository import SqlAuditLogRepository
from app.infrastructure.persistence.catalog_image_repository import SqlCatalogImageRepository
from app.infrastructure.persistence.catalog_image_slot_repository import (
    SqlCatalogImageSlotRepository,
)
from app.infrastructure.persistence.catalog_slot_input_requirement_repository import (
    SqlCatalogSlotInputRequirementRepository,
)
from app.infrastructure.persistence.catalog_template_repository import (
    SqlCatalogTemplateRepository,
)
from app.infrastructure.persistence.category_repository import SqlCategoryRepository
from app.infrastructure.persistence.category_spec_version_repository import (
    SqlCategorySpecVersionRepository,
)
from app.infrastructure.persistence.content_draft_repository import SqlContentDraftRepository
from app.infrastructure.persistence.generation_item_repository import (
    SqlGenerationItemRepository,
)
from app.infrastructure.persistence.generation_request_repository import (
    SqlGenerationRequestRepository,
)
from app.infrastructure.persistence.idempotency_repository import SqlIdempotencyRepository
from app.infrastructure.persistence.identity_repository import SqlIdentityRepository
from app.infrastructure.persistence.input_image_slot_repository import (
    SqlInputImageSlotRepository,
)
from app.infrastructure.persistence.outbox_event_repository import SqlOutboxEventRepository
from app.infrastructure.persistence.platform_admin_repository import SqlPlatformAdminRepository
from app.infrastructure.persistence.product_input_image_repository import (
    SqlProductInputImageRepository,
)
from app.infrastructure.persistence.product_repository import SqlProductRepository
from app.infrastructure.persistence.product_variant_repository import (
    SqlProductVariantRepository,
)
from app.infrastructure.persistence.quota_reservation_repository import (
    SqlQuotaReservationRepository,
)
from app.infrastructure.persistence.session_repository import SqlSessionRepository
from app.infrastructure.persistence.settings_repository import SqlSettingsRepository
from app.infrastructure.persistence.task_queue import SqlTaskQueue
from app.infrastructure.persistence.tenant_membership_repository import (
    SqlTenantMembershipRepository,
)
from app.infrastructure.persistence.tenant_repository import SqlTenantRepository
from app.infrastructure.persistence.tenant_scope import bind_tenant
from app.infrastructure.persistence.user_repository import SqlUserRepository
from app.infrastructure.persistence.variant_axis_repository import SqlVariantAxisRepository
from app.infrastructure.persistence.variant_axis_value_repository import (
    SqlVariantAxisValueRepository,
)
from app.services.ports.asset_repository import AssetRepository
from app.services.ports.attribute_definition_repository import AttributeDefinitionRepository
from app.services.ports.audit_log_repository import AuditLogRepository
from app.services.ports.catalog_image_repository import CatalogImageRepository
from app.services.ports.catalog_image_slot_repository import CatalogImageSlotRepository
from app.services.ports.catalog_slot_input_requirement_repository import (
    CatalogSlotInputRequirementRepository,
)
from app.services.ports.catalog_template_repository import CatalogTemplateRepository
from app.services.ports.category_repository import CategoryRepository
from app.services.ports.category_spec_version_repository import CategorySpecVersionRepository
from app.services.ports.content_draft_repository import ContentDraftRepository
from app.services.ports.generation_item_repository import GenerationItemRepository
from app.services.ports.generation_request_repository import GenerationRequestRepository
from app.services.ports.idempotency_repository import IdempotencyRepository
from app.services.ports.identity_repository import IdentityRepository
from app.services.ports.input_image_slot_repository import InputImageSlotRepository
from app.services.ports.outbox_event_repository import OutboxEventRepository
from app.services.ports.platform_admin_repository import PlatformAdminRepository
from app.services.ports.product_input_image_repository import ProductInputImageRepository
from app.services.ports.product_repository import ProductRepository
from app.services.ports.product_variant_repository import ProductVariantRepository
from app.services.ports.quota_reservation_repository import QuotaReservationRepository
from app.services.ports.session_repository import SessionRepository
from app.services.ports.settings_repository import SettingsRepository
from app.services.ports.task_queue import TaskQueue
from app.services.ports.tenant_membership_repository import TenantMembershipRepository
from app.services.ports.tenant_repository import TenantRepository
from app.services.ports.user_repository import UserRepository
from app.services.ports.variant_axis_repository import VariantAxisRepository
from app.services.ports.variant_axis_value_repository import VariantAxisValueRepository
from app.shared.ids import TenantId


class SqlUnitOfWork:
    """Implements ``app.services.ports.unit_of_work.UnitOfWork``.

    Not declared as inheriting the ``Protocol`` — structural typing means this
    satisfies the port by shape, per the pattern in CLAUDE.md §14.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        tenant_id: TenantId | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._tenant_id = tenant_id
        self._session: AsyncSession | None = None
        # Built lazily, once, on first access - repositories are cheap,
        # stateless wrappers around the session, but there is no reason to
        # rebuild one every time a use case touches the same property twice.
        self._users: SqlUserRepository | None = None
        self._identities: SqlIdentityRepository | None = None
        self._platform_admins: SqlPlatformAdminRepository | None = None
        self._tenant_memberships: SqlTenantMembershipRepository | None = None
        self._sessions: SqlSessionRepository | None = None
        self._idempotency_keys: SqlIdempotencyRepository | None = None
        self._audit_log: SqlAuditLogRepository | None = None
        self._categories: SqlCategoryRepository | None = None
        self._attribute_definitions: SqlAttributeDefinitionRepository | None = None
        self._variant_axes: SqlVariantAxisRepository | None = None
        self._variant_axis_values: SqlVariantAxisValueRepository | None = None
        self._input_image_slots: SqlInputImageSlotRepository | None = None
        self._catalog_image_slots: SqlCatalogImageSlotRepository | None = None
        self._catalog_slot_input_requirements: SqlCatalogSlotInputRequirementRepository | None = (
            None
        )
        self._category_spec_versions: SqlCategorySpecVersionRepository | None = None
        self._settings: SqlSettingsRepository | None = None
        self._assets: SqlAssetRepository | None = None
        self._catalog_templates: SqlCatalogTemplateRepository | None = None
        self._products: SqlProductRepository | None = None
        self._product_variants: SqlProductVariantRepository | None = None
        self._product_input_images: SqlProductInputImageRepository | None = None
        self._outbox_events: SqlOutboxEventRepository | None = None
        self._task_queue: SqlTaskQueue | None = None
        self._tenants: SqlTenantRepository | None = None
        self._quota_reservations: SqlQuotaReservationRepository | None = None
        self._generation_requests: SqlGenerationRequestRepository | None = None
        self._generation_items: SqlGenerationItemRepository | None = None
        self._catalog_images: SqlCatalogImageRepository | None = None
        self._content_drafts: SqlContentDraftRepository | None = None

    @property
    def session(self) -> AsyncSession:
        """Only for adapters constructed by ``bootstrap``, which knows the
        concrete SQL implementation is in play. Ports never expose this."""
        if self._session is None:
            raise RuntimeError("SqlUnitOfWork used outside its `async with` block")
        return self._session

    @property
    def users(self) -> UserRepository:
        if self._users is None:
            self._users = SqlUserRepository(self.session)
        return self._users

    @property
    def identities(self) -> IdentityRepository:
        if self._identities is None:
            self._identities = SqlIdentityRepository(self.session)
        return self._identities

    @property
    def platform_admins(self) -> PlatformAdminRepository:
        if self._platform_admins is None:
            self._platform_admins = SqlPlatformAdminRepository(self.session)
        return self._platform_admins

    @property
    def tenant_memberships(self) -> TenantMembershipRepository:
        if self._tenant_memberships is None:
            self._tenant_memberships = SqlTenantMembershipRepository(self.session)
        return self._tenant_memberships

    @property
    def sessions(self) -> SessionRepository:
        if self._sessions is None:
            self._sessions = SqlSessionRepository(self.session)
        return self._sessions

    @property
    def idempotency_keys(self) -> IdempotencyRepository:
        if self._idempotency_keys is None:
            self._idempotency_keys = SqlIdempotencyRepository(self.session)
        return self._idempotency_keys

    @property
    def audit_log(self) -> AuditLogRepository:
        if self._audit_log is None:
            self._audit_log = SqlAuditLogRepository(self.session)
        return self._audit_log

    @property
    def categories(self) -> CategoryRepository:
        if self._categories is None:
            self._categories = SqlCategoryRepository(self.session)
        return self._categories

    @property
    def attribute_definitions(self) -> AttributeDefinitionRepository:
        if self._attribute_definitions is None:
            self._attribute_definitions = SqlAttributeDefinitionRepository(self.session)
        return self._attribute_definitions

    @property
    def variant_axes(self) -> VariantAxisRepository:
        if self._variant_axes is None:
            self._variant_axes = SqlVariantAxisRepository(self.session)
        return self._variant_axes

    @property
    def variant_axis_values(self) -> VariantAxisValueRepository:
        if self._variant_axis_values is None:
            self._variant_axis_values = SqlVariantAxisValueRepository(self.session)
        return self._variant_axis_values

    @property
    def input_image_slots(self) -> InputImageSlotRepository:
        if self._input_image_slots is None:
            self._input_image_slots = SqlInputImageSlotRepository(self.session)
        return self._input_image_slots

    @property
    def catalog_image_slots(self) -> CatalogImageSlotRepository:
        if self._catalog_image_slots is None:
            self._catalog_image_slots = SqlCatalogImageSlotRepository(self.session)
        return self._catalog_image_slots

    @property
    def catalog_slot_input_requirements(self) -> CatalogSlotInputRequirementRepository:
        if self._catalog_slot_input_requirements is None:
            self._catalog_slot_input_requirements = SqlCatalogSlotInputRequirementRepository(
                self.session
            )
        return self._catalog_slot_input_requirements

    @property
    def category_spec_versions(self) -> CategorySpecVersionRepository:
        if self._category_spec_versions is None:
            self._category_spec_versions = SqlCategorySpecVersionRepository(self.session)
        return self._category_spec_versions

    @property
    def settings(self) -> SettingsRepository:
        if self._settings is None:
            self._settings = SqlSettingsRepository(self.session)
        return self._settings

    @property
    def assets(self) -> AssetRepository:
        if self._assets is None:
            self._assets = SqlAssetRepository(self.session)
        return self._assets

    @property
    def catalog_templates(self) -> CatalogTemplateRepository:
        if self._catalog_templates is None:
            self._catalog_templates = SqlCatalogTemplateRepository(self.session)
        return self._catalog_templates

    @property
    def products(self) -> ProductRepository:
        if self._products is None:
            self._products = SqlProductRepository(self.session)
        return self._products

    @property
    def product_variants(self) -> ProductVariantRepository:
        if self._product_variants is None:
            self._product_variants = SqlProductVariantRepository(self.session)
        return self._product_variants

    @property
    def product_input_images(self) -> ProductInputImageRepository:
        if self._product_input_images is None:
            self._product_input_images = SqlProductInputImageRepository(self.session)
        return self._product_input_images

    @property
    def outbox_events(self) -> OutboxEventRepository:
        if self._outbox_events is None:
            self._outbox_events = SqlOutboxEventRepository(self.session)
        return self._outbox_events

    @property
    def task_queue(self) -> TaskQueue:
        if self._task_queue is None:
            self._task_queue = SqlTaskQueue(self.session)
        return self._task_queue

    @property
    def tenants(self) -> TenantRepository:
        if self._tenants is None:
            self._tenants = SqlTenantRepository(self.session)
        return self._tenants

    @property
    def quota_reservations(self) -> QuotaReservationRepository:
        if self._quota_reservations is None:
            self._quota_reservations = SqlQuotaReservationRepository(self.session)
        return self._quota_reservations

    @property
    def generation_requests(self) -> GenerationRequestRepository:
        if self._generation_requests is None:
            self._generation_requests = SqlGenerationRequestRepository(self.session)
        return self._generation_requests

    @property
    def generation_items(self) -> GenerationItemRepository:
        if self._generation_items is None:
            self._generation_items = SqlGenerationItemRepository(self.session)
        return self._generation_items

    @property
    def catalog_images(self) -> CatalogImageRepository:
        if self._catalog_images is None:
            self._catalog_images = SqlCatalogImageRepository(self.session)
        return self._catalog_images

    @property
    def content_drafts(self) -> ContentDraftRepository:
        if self._content_drafts is None:
            self._content_drafts = SqlContentDraftRepository(self.session)
        return self._content_drafts

    async def __aenter__(self) -> SqlUnitOfWork:
        session = self._session_factory()
        await session.begin()
        if self._tenant_id is not None:
            await bind_tenant(session, self._tenant_id)
        self._session = session
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self.session  # raises if __aenter__ was never called
        try:
            if exc_type is None:
                await session.commit()
            else:
                await session.rollback()
        finally:
            await session.close()
            self._session = None
            # Each cached repository holds the now-closed session; drop them
            # so a defensive re-entry (not the normal case - the factory
            # hands out a fresh instance each time) cannot return one bound
            # to a dead connection.
            self._users = None
            self._identities = None
            self._platform_admins = None
            self._tenant_memberships = None
            self._sessions = None
            self._idempotency_keys = None
            self._audit_log = None
            self._categories = None
            self._attribute_definitions = None
            self._variant_axes = None
            self._variant_axis_values = None
            self._input_image_slots = None
            self._catalog_image_slots = None
            self._catalog_slot_input_requirements = None
            self._category_spec_versions = None
            self._settings = None
            self._assets = None
            self._catalog_templates = None
            self._products = None
            self._product_variants = None
            self._product_input_images = None
            self._outbox_events = None
            self._task_queue = None
            self._tenants = None
            self._quota_reservations = None
            self._generation_requests = None
            self._generation_items = None
            self._catalog_images = None
            self._content_drafts = None


def make_unit_of_work_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[TenantId | None], SqlUnitOfWork]:
    """Satisfies ``UnitOfWorkFactory``. A named function rather than a
    ``lambda`` bound inline in ``bootstrap``, so it appears in a traceback
    with an intention-revealing name.
    """

    def factory(tenant_id: TenantId | None = None) -> SqlUnitOfWork:
        return SqlUnitOfWork(session_factory, tenant_id)

    return factory
