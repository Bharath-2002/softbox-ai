"""RefreshSession — rotation and, specifically, reuse detection.

The reuse-detection tests are the important ones in this file: a rotated-away
token being presented again must revoke the *entire* session
(``revoke_all_for_user``), not just fail the one call, per the advisor
guidance this design followed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.entities.session import Session
from app.features.identity.refresh_session import RefreshSession
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.shared.errors import AuthenticationError
from app.shared.ids import new_session_id, new_user_id
from app.shared.tokens import generate_token, hash_token
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"


def _use_case() -> tuple[RefreshSession, FakeClock, FakeUnitOfWorkFactory]:
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    return RefreshSession(codec, uow_factory, clock), clock, uow_factory


async def _seed_session(
    uow_factory: FakeUnitOfWorkFactory, clock: FakeClock, *, token: str
) -> Session:
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
    return session


async def test_unknown_token_is_rejected() -> None:
    use_case, _clock, _uow = _use_case()

    with pytest.raises(AuthenticationError, match="Invalid refresh token"):
        await use_case(refresh_token="never-issued")


async def test_valid_refresh_rotates_the_token() -> None:
    use_case, clock, uow_factory = _use_case()
    original_token = generate_token()
    session = await _seed_session(uow_factory, clock, token=original_token)

    result = await use_case(refresh_token=original_token)

    assert result.refresh_token != original_token
    stored = await uow_factory.sessions.get_by_refresh_token_hash(hash_token(result.refresh_token))
    assert stored is not None
    assert stored.id == session.id


async def test_the_old_token_is_no_longer_the_current_hash_after_rotation() -> None:
    use_case, clock, uow_factory = _use_case()
    original_token = generate_token()
    await _seed_session(uow_factory, clock, token=original_token)

    await use_case(refresh_token=original_token)

    assert await uow_factory.sessions.get_by_refresh_token_hash(hash_token(original_token)) is None


async def test_rotation_chain_continues_with_the_new_token() -> None:
    use_case, clock, uow_factory = _use_case()
    original_token = generate_token()
    await _seed_session(uow_factory, clock, token=original_token)

    first = await use_case(refresh_token=original_token)
    second = await use_case(refresh_token=first.refresh_token)

    assert second.refresh_token != first.refresh_token
    assert second.refresh_token != original_token


async def test_replaying_a_rotated_away_token_is_rejected() -> None:
    use_case, clock, uow_factory = _use_case()
    original_token = generate_token()
    await _seed_session(uow_factory, clock, token=original_token)
    await use_case(refresh_token=original_token)  # rotates it away

    with pytest.raises(AuthenticationError, match=r"reuse|revoked|Invalid"):
        await use_case(refresh_token=original_token)  # replay


async def test_replaying_a_rotated_away_token_revokes_the_whole_session_not_just_the_call() -> None:
    """The specific property this design exists for: the response to a
    replayed token is not "that one call failed" but "this session is now
    dead" - confirmed by checking the CURRENT valid token stops working too,
    not by inspecting revoked_at directly (that would only prove the field
    was set, not that it actually locks the session out)."""
    use_case, clock, uow_factory = _use_case()
    original_token = generate_token()
    await _seed_session(uow_factory, clock, token=original_token)
    rotated = await use_case(refresh_token=original_token)

    with pytest.raises(AuthenticationError):
        await use_case(refresh_token=original_token)  # the replay

    # The token that was legitimately valid a moment ago must also be dead now.
    with pytest.raises(AuthenticationError, match=r"no longer active|Invalid"):
        await use_case(refresh_token=rotated.refresh_token)


async def test_an_expired_session_is_rejected() -> None:
    use_case, clock, uow_factory = _use_case()
    token = generate_token()
    session = Session(
        id=new_session_id(),
        user_id=new_user_id(),
        tenant_id=None,
        refresh_token_hash=hash_token(token),
        previous_token_hash=None,
        expires_at=clock.now() - timedelta(seconds=1),  # already expired
        revoked_at=None,
        created_at=clock.now(),
    )
    await uow_factory.sessions.add(session)

    with pytest.raises(AuthenticationError, match="no longer active"):
        await use_case(refresh_token=token)


async def test_the_new_access_token_carries_the_sessions_user() -> None:
    use_case, clock, uow_factory = _use_case()
    token = generate_token()
    session = await _seed_session(uow_factory, clock, token=token)

    result = await use_case(refresh_token=token)

    codec = AccessTokenCodec(SIGNING_KEY)
    decoded = codec.decode(result.access_token, now=clock.now())
    assert decoded.subject == str(session.user_id)
