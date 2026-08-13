"""StartImpersonation — issues an audited, time-boxed token letting a
platform admin act as a specific tenant member.

Authorization (is the caller actually a platform admin) is the route's job
(``require_platform_admin``), not this use case's — these tests call it
directly with an arbitrary ``admin_user_id``, the same way ``CompleteLogin``'s
tests never check who is allowed to log in.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.roles import Role
from app.entities.tenant_membership import TenantMembership
from app.features.identity.start_impersonation import StartImpersonation
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.shared.errors import NotFoundError
from app.shared.ids import new_tenant_id, new_tenant_membership_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"


def _use_case() -> tuple[StartImpersonation, FakeClock, FakeUnitOfWorkFactory, AccessTokenCodec]:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    return StartImpersonation(codec, uow_factory, clock), clock, uow_factory, codec


async def test_issues_a_token_carrying_the_targets_role_and_capabilities() -> None:
    use_case, clock, uow_factory, codec = _use_case()
    admin_id = new_user_id()
    target_id = new_user_id()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_memberships.add(
        TenantMembership(
            id=new_tenant_membership_id(),
            tenant_id=tenant_id,
            user_id=target_id,
            role=Role.CATALOG_MANAGER,
            extra_capabilities=[],
            created_at=clock.now(),
        )
    )

    result = await use_case(
        admin_user_id=admin_id,
        target_user_id=target_id,
        target_tenant_id=tenant_id,
        reason="Investigating a support ticket.",
    )

    decoded = codec.decode(result.access_token, now=clock.now())
    assert decoded.subject == str(target_id)
    assert decoded.tenant_id == str(tenant_id)
    assert decoded.role == "catalog_manager"
    assert "catalog.publish" in decoded.capabilities


async def test_the_issued_token_carries_impersonated_by_and_never_platform_admin() -> None:
    """The security-critical property: acting AS the target, never WITH the
    admin's own platform-wide power layered on top."""
    use_case, clock, uow_factory, codec = _use_case()
    admin_id = new_user_id()
    target_id = new_user_id()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_memberships.add(
        TenantMembership(
            id=new_tenant_membership_id(),
            tenant_id=tenant_id,
            user_id=target_id,
            role=Role.VIEWER,
            extra_capabilities=[],
            created_at=clock.now(),
        )
    )
    await uow_factory.platform_admins.grant(admin_id, granted_by=admin_id, now=clock.now())

    result = await use_case(
        admin_user_id=admin_id, target_user_id=target_id, target_tenant_id=tenant_id, reason="r"
    )

    decoded = codec.decode(result.access_token, now=clock.now())
    assert decoded.impersonated_by == str(admin_id)
    assert decoded.is_platform_admin is False


async def test_a_target_with_no_membership_in_the_tenant_is_rejected() -> None:
    use_case, _clock, _uow, _codec = _use_case()

    with pytest.raises(NotFoundError, match="not a member"):
        await use_case(
            admin_user_id=new_user_id(),
            target_user_id=new_user_id(),
            target_tenant_id=new_tenant_id(),
            reason="r",
        )


async def test_no_refresh_token_is_issued() -> None:
    """Deliberate: impersonation cannot be silently extended past the
    access token's own short expiry - resuming means going through this
    audited path again."""
    use_case, clock, uow_factory, _codec = _use_case()
    admin_id = new_user_id()
    target_id = new_user_id()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_memberships.add(
        TenantMembership(
            id=new_tenant_membership_id(),
            tenant_id=tenant_id,
            user_id=target_id,
            role=Role.VIEWER,
            extra_capabilities=[],
            created_at=clock.now(),
        )
    )

    result = await use_case(
        admin_user_id=admin_id, target_user_id=target_id, target_tenant_id=tenant_id, reason="r"
    )

    assert not hasattr(result, "refresh_token")


async def test_writes_an_audit_log_entry_with_the_real_admin_as_actor() -> None:
    use_case, clock, uow_factory, _codec = _use_case()
    admin_id = new_user_id()
    target_id = new_user_id()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_memberships.add(
        TenantMembership(
            id=new_tenant_membership_id(),
            tenant_id=tenant_id,
            user_id=target_id,
            role=Role.VIEWER,
            extra_capabilities=[],
            created_at=clock.now(),
        )
    )

    await use_case(
        admin_user_id=admin_id,
        target_user_id=target_id,
        target_tenant_id=tenant_id,
        reason="Investigating a support ticket.",
    )

    entries = await uow_factory.audit_log.list_for_subject(tenant_id, "user", target_id)
    assert len(entries) == 1
    assert entries[0].actor_user_id == admin_id
    assert entries[0].action == "impersonation.started"
    assert entries[0].after == {"reason": "Investigating a support ticket."}


async def test_a_rejected_target_writes_no_audit_entry() -> None:
    """Nothing worth auditing happened - the impersonation never started."""
    use_case, _clock, uow_factory, _codec = _use_case()
    tenant_id = new_tenant_id()

    with pytest.raises(NotFoundError):
        await use_case(
            admin_user_id=new_user_id(),
            target_user_id=new_user_id(),
            target_tenant_id=tenant_id,
            reason="r",
        )

    assert uow_factory.audit_log._rows == []
