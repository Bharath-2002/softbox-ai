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
from tests.fakes.attribute_definition_repository import InMemoryAttributeDefinitionRepository
from tests.fakes.audit_log_repository import InMemoryAuditLogRepository
from tests.fakes.catalog_image_slot_repository import InMemoryCatalogImageSlotRepository
from tests.fakes.category_repository import InMemoryCategoryRepository
from tests.fakes.idempotency_repository import InMemoryIdempotencyRepository
from tests.fakes.identity_repository import InMemoryIdentityRepository
from tests.fakes.input_image_slot_repository import InMemoryInputImageSlotRepository
from tests.fakes.platform_admin_repository import InMemoryPlatformAdminRepository
from tests.fakes.session_repository import InMemorySessionRepository
from tests.fakes.tenant_membership_repository import InMemoryTenantMembershipRepository
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
            tenant_id=tenant_id,
        )


def fake_unit_of_work_factory() -> Callable[[TenantId | None], FakeUnitOfWork]:
    return FakeUnitOfWorkFactory()
