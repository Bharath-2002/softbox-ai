from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.entities.session import Session
from app.features.identity.logout import Logout
from app.shared.ids import new_session_id, new_user_id
from app.shared.tokens import generate_token, hash_token
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory


def _use_case() -> tuple[Logout, FakeClock, FakeUnitOfWorkFactory]:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    return Logout(uow_factory, clock), clock, uow_factory


async def test_logout_revokes_the_session() -> None:
    use_case, clock, uow_factory = _use_case()
    token = generate_token()
    session = Session(
        id=new_session_id(),
        user_id=new_user_id(),
        tenant_id=None,
        refresh_token_hash=hash_token(token),
        previous_token_hash=None,
        expires_at=clock.now() + timedelta(days=30),
        revoked_at=None,
        created_at=clock.now(),
    )
    await uow_factory.sessions.add(session)

    await use_case(refresh_token=token)

    refreshed = await uow_factory.sessions.get_by_refresh_token_hash(hash_token(token))
    assert refreshed is not None
    assert refreshed.revoked_at is not None


async def test_logout_with_an_unknown_token_is_not_an_error() -> None:
    use_case, _clock, _uow = _use_case()

    await use_case(refresh_token="never-issued")  # must not raise


async def test_logout_is_idempotent_on_an_already_revoked_session() -> None:
    use_case, clock, uow_factory = _use_case()
    token = generate_token()
    first_revocation = clock.now()
    session = Session(
        id=new_session_id(),
        user_id=new_user_id(),
        tenant_id=None,
        refresh_token_hash=hash_token(token),
        previous_token_hash=None,
        expires_at=clock.now() + timedelta(days=30),
        revoked_at=first_revocation,
        created_at=clock.now(),
    )
    await uow_factory.sessions.add(session)

    clock.advance(timedelta(minutes=5))
    await use_case(refresh_token=token)  # must not raise, and must not overwrite revoked_at

    refreshed = await uow_factory.sessions.get_by_refresh_token_hash(hash_token(token))
    assert refreshed is not None
    assert refreshed.revoked_at == first_revocation
