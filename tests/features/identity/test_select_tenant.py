"""SelectTenant — the one place a session's ``tenant_id`` is ever set to
something other than ``None`` (see the module's own docstring). Shares
``RefreshSession``'s rotate-on-use and reuse-detection shape; this file
covers what's new here — the membership check and the resulting token's
tenant/role/capabilities — and leans on ``test_refresh_session.py``'s
existing coverage for reuse detection rather than duplicating it.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.entities.roles import Role
from app.entities.session import Session
from app.entities.tenant_membership import TenantMembership
from app.features.identity.select_tenant import SelectTenant
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.shared.errors import AuthenticationError, PermissionDeniedError
from app.shared.ids import UserId, new_session_id, new_tenant_id, new_user_id
from app.shared.tokens import generate_token, hash_token
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"


def _use_case() -> tuple[SelectTenant, FakeClock, FakeUnitOfWorkFactory]:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    return SelectTenant(codec, uow_factory, clock), clock, uow_factory


async def _seed_session(
    uow_factory: FakeUnitOfWorkFactory,
    clock: FakeClock,
    *,
    token: str,
    user_id: UserId | None = None,
) -> Session:
    session = Session(
        id=new_session_id(),
        user_id=user_id if user_id is not None else new_user_id(),
        tenant_id=None,
        refresh_token_hash=hash_token(token),
        previous_token_hash=None,
        expires_at=clock.now() + timedelta(days=30),
        revoked_at=None,
        created_at=clock.now(),
    )
    await uow_factory.sessions.add(session)
    return session


async def test_unknown_token_is_rejected() -> None:
    use_case, _clock, _uow = _use_case()

    with pytest.raises(AuthenticationError, match="Invalid refresh token"):
        await use_case(refresh_token="never-issued", tenant_id=new_tenant_id())


async def test_selecting_a_tenant_with_no_membership_is_denied() -> None:
    use_case, clock, uow_factory = _use_case()
    token = generate_token()
    await _seed_session(uow_factory, clock, token=token)

    with pytest.raises(PermissionDeniedError):
        await use_case(refresh_token=token, tenant_id=new_tenant_id())


async def test_selecting_a_tenant_with_membership_issues_a_scoped_token() -> None:
    use_case, clock, uow_factory = _use_case()
    token = generate_token()
    user_id = new_user_id()
    session = await _seed_session(uow_factory, clock, token=token, user_id=user_id)
    tenant_id = new_tenant_id()
    await uow_factory.tenant_memberships.add(
        TenantMembership.create(tenant_id, user_id, role=Role.OWNER, now=clock.now())
    )

    result = await use_case(refresh_token=token, tenant_id=tenant_id)

    codec = AccessTokenCodec(SIGNING_KEY)
    decoded = codec.decode(result.access_token, now=clock.now())
    assert decoded.subject == str(session.user_id)
    assert decoded.tenant_id == str(tenant_id)
    assert decoded.role == "owner"
    assert "product.manage" in decoded.capabilities


async def test_the_session_is_updated_with_the_selected_tenant() -> None:
    use_case, clock, uow_factory = _use_case()
    token = generate_token()
    user_id = new_user_id()
    session = await _seed_session(uow_factory, clock, token=token, user_id=user_id)
    tenant_id = new_tenant_id()
    await uow_factory.tenant_memberships.add(
        TenantMembership.create(tenant_id, user_id, role=Role.OWNER, now=clock.now())
    )

    result = await use_case(refresh_token=token, tenant_id=tenant_id)

    stored = await uow_factory.sessions.get_by_refresh_token_hash(hash_token(result.refresh_token))
    assert stored is not None
    assert stored.id == session.id
    assert stored.tenant_id == tenant_id


async def test_selecting_a_tenant_rotates_the_refresh_token() -> None:
    use_case, clock, uow_factory = _use_case()
    token = generate_token()
    user_id = new_user_id()
    await _seed_session(uow_factory, clock, token=token, user_id=user_id)
    tenant_id = new_tenant_id()
    await uow_factory.tenant_memberships.add(
        TenantMembership.create(tenant_id, user_id, role=Role.OWNER, now=clock.now())
    )

    result = await use_case(refresh_token=token, tenant_id=tenant_id)

    assert result.refresh_token != token
    assert await uow_factory.sessions.get_by_refresh_token_hash(hash_token(token)) is None


async def test_an_expired_session_is_rejected() -> None:
    use_case, clock, uow_factory = _use_case()
    token = generate_token()
    session = Session(
        id=new_session_id(),
        user_id=new_user_id(),
        tenant_id=None,
        refresh_token_hash=hash_token(token),
        previous_token_hash=None,
        expires_at=clock.now() - timedelta(seconds=1),
        revoked_at=None,
        created_at=clock.now(),
    )
    await uow_factory.sessions.add(session)

    with pytest.raises(AuthenticationError, match="no longer active"):
        await use_case(refresh_token=token, tenant_id=new_tenant_id())
