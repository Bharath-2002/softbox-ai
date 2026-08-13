"""PrincipalResolver against the in-memory fakes — pure domain-service logic,
no database needed.
"""

from __future__ import annotations

from app.entities.capabilities import Capability
from app.entities.roles import Role
from app.entities.tenant_membership import TenantMembership
from app.entities.user import User
from app.services.principal_resolver import PrincipalResolver
from app.shared.clock import utcnow
from app.shared.ids import new_tenant_id, new_user_id
from tests.fakes.platform_admin_repository import InMemoryPlatformAdminRepository
from tests.fakes.tenant_membership_repository import InMemoryTenantMembershipRepository
from tests.fakes.user_repository import InMemoryUserRepository


def _resolver() -> tuple[
    PrincipalResolver, InMemoryTenantMembershipRepository, InMemoryPlatformAdminRepository
]:
    memberships = InMemoryTenantMembershipRepository()
    admins = InMemoryPlatformAdminRepository()
    return PrincipalResolver(memberships, admins), memberships, admins


async def test_no_tenant_requested_yields_no_role_or_capabilities() -> None:
    resolver, _memberships, _admins = _resolver()
    user_id = new_user_id()

    principal = await resolver.resolve(user_id, None)

    assert principal.tenant_id is None
    assert principal.role is None
    assert principal.capabilities == frozenset()


async def test_non_member_gets_no_capabilities_in_that_tenant() -> None:
    resolver, _memberships, _admins = _resolver()
    user_id = new_user_id()
    tenant_id = new_tenant_id()

    principal = await resolver.resolve(user_id, tenant_id)

    assert principal.role is None
    assert principal.capabilities == frozenset()


async def test_member_resolves_the_roles_capabilities() -> None:
    resolver, memberships, _admins = _resolver()
    user_id = new_user_id()
    tenant_id = new_tenant_id()
    await memberships.add(
        TenantMembership.create(tenant_id, user_id, role=Role.APPROVER, now=utcnow())
    )

    principal = await resolver.resolve(user_id, tenant_id)

    assert principal.role == Role.APPROVER
    assert principal.has_capability(Capability.CATALOG_APPROVE)
    assert not principal.has_capability(Capability.CATALOG_PUBLISH)


async def test_extra_capabilities_are_merged_onto_the_role() -> None:
    resolver, memberships, _admins = _resolver()
    user_id = new_user_id()
    tenant_id = new_tenant_id()
    await memberships.add(
        TenantMembership.create(
            tenant_id,
            user_id,
            role=Role.VIEWER,
            now=utcnow(),
            extra_capabilities=["one-off-grant"],
        )
    )

    principal = await resolver.resolve(user_id, tenant_id)

    # The role's own set stays empty; the extra grant is additive, not a
    # promotion to a different role.
    assert not principal.has_capability(Capability.CATALOG_PUBLISH)
    assert principal.has_capability("one-off-grant")


async def test_platform_admin_flag_is_independent_of_tenant_membership() -> None:
    resolver, _memberships, admins = _resolver()
    user_id = new_user_id()
    tenant_id = new_tenant_id()
    await admins.grant(user_id, granted_by=new_user_id(), now=utcnow())

    principal = await resolver.resolve(user_id, tenant_id)

    assert principal.is_platform_admin is True
    # D4, generalised: platform-admin status alone grants no tenant
    # capability. Confirmed at the resolver, not just on Principal directly -
    # the actual repository lookup path must produce this too.
    assert principal.role is None
    assert principal.capabilities == frozenset()


async def test_company_domain_email_with_no_grant_is_not_a_platform_admin() -> None:
    """The exact D4 property: domain match alone is never sufficient. A real
    User row with a company-domain email exists; there is still no
    `platform_admins` row for them, and no code path here that even looks at
    the email domain to decide otherwise."""
    resolver, _memberships, _admins = _resolver()
    users = InMemoryUserRepository()
    employee = User.register("founder@softbox-ai.example", now=utcnow())
    await users.add(employee)

    principal = await resolver.resolve(employee.id, None)

    assert principal.is_platform_admin is False
