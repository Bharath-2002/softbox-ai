"""The transaction boundary.

One use case, one transaction — ``features`` opens exactly one ``UnitOfWork``
per call. The implementation is responsible for the tenant isolation guard
(D3): every statement run inside the transaction must see
``current_setting('app.current_tenant')`` set via ``SET LOCAL``, scoped to that
transaction, before any tenant-scoped query runs.

``tenant_id=None`` is for genuinely tenant-free work — platform-plane
operations, and the migrations/bootstrap paths that run as the owner role.
Everything else must pass a tenant.

Repositories are properties on the open ``UnitOfWork``
(``uow.users``, ``uow.sessions``, ...), not separate constructor arguments a
use case is handed alongside it. The alternative — inject each repository
into the use case's constructor, already bound to a session — only works if
something constructs that session *before* the use case runs and hands
repositories and the ``UnitOfWork`` the same one. Nothing in this codebase
does that (``SqlUnitOfWork`` owns its own session, created in
``__aenter__``), and building that per-request-session plumbing now would
mean rewriting every already-shipped, already-tested caller of
``SqlUnitOfWork`` to fit a session it does not yet have when constructed.
Properties on the open unit of work need none of that — each is built lazily
from ``self.session`` once ``__aenter__`` has run, additively, and match the
classic "Unit of Work exposes its repositories" pattern directly.

This list grows by one property per repository as new ones are added — an
open-ended surface, accepted deliberately as the cost of not rewriting
already-shipped code for a different pattern that has no other advantage
here.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.services.ports.asset_repository import AssetRepository
from app.services.ports.attribute_definition_repository import AttributeDefinitionRepository
from app.services.ports.audit_log_repository import AuditLogRepository
from app.services.ports.catalog_image_slot_repository import CatalogImageSlotRepository
from app.services.ports.catalog_slot_input_requirement_repository import (
    CatalogSlotInputRequirementRepository,
)
from app.services.ports.catalog_template_repository import CatalogTemplateRepository
from app.services.ports.category_repository import CategoryRepository
from app.services.ports.category_spec_version_repository import CategorySpecVersionRepository
from app.services.ports.idempotency_repository import IdempotencyRepository
from app.services.ports.identity_repository import IdentityRepository
from app.services.ports.input_image_slot_repository import InputImageSlotRepository
from app.services.ports.platform_admin_repository import PlatformAdminRepository
from app.services.ports.session_repository import SessionRepository
from app.services.ports.settings_repository import SettingsRepository
from app.services.ports.tenant_membership_repository import TenantMembershipRepository
from app.services.ports.user_repository import UserRepository
from app.services.ports.variant_axis_repository import VariantAxisRepository
from app.services.ports.variant_axis_value_repository import VariantAxisValueRepository
from app.shared.ids import TenantId


class UnitOfWork(Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def identities(self) -> IdentityRepository: ...

    @property
    def platform_admins(self) -> PlatformAdminRepository: ...

    @property
    def tenant_memberships(self) -> TenantMembershipRepository: ...

    @property
    def sessions(self) -> SessionRepository: ...

    @property
    def idempotency_keys(self) -> IdempotencyRepository: ...

    @property
    def audit_log(self) -> AuditLogRepository: ...

    @property
    def categories(self) -> CategoryRepository: ...

    @property
    def attribute_definitions(self) -> AttributeDefinitionRepository: ...

    @property
    def variant_axes(self) -> VariantAxisRepository: ...

    @property
    def variant_axis_values(self) -> VariantAxisValueRepository: ...

    @property
    def input_image_slots(self) -> InputImageSlotRepository: ...

    @property
    def catalog_image_slots(self) -> CatalogImageSlotRepository: ...

    @property
    def catalog_slot_input_requirements(self) -> CatalogSlotInputRequirementRepository: ...

    @property
    def category_spec_versions(self) -> CategorySpecVersionRepository: ...

    @property
    def settings(self) -> SettingsRepository: ...

    @property
    def assets(self) -> AssetRepository: ...

    @property
    def catalog_templates(self) -> CatalogTemplateRepository: ...

    async def __aenter__(self) -> UnitOfWork:
        """Begin the transaction and apply the tenant scope."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Commit on a clean exit, roll back if the block raised."""
        ...


class UnitOfWorkFactory(Protocol):
    """What a use case actually depends on — it asks for a scoped unit of work
    rather than being handed an already-open one, so it controls exactly one
    transaction's lifetime."""

    def __call__(self, tenant_id: TenantId | None = None) -> UnitOfWork: ...
