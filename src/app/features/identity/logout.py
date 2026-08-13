"""Revokes one session (D4).

Idempotent by design: presenting an already-invalid or unknown token is not
an error — the caller wanted to be logged out, and after this call they are,
regardless of whether the token was still valid to begin with.
"""

from __future__ import annotations

from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.tokens import hash_token


class Logout:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, refresh_token: str) -> None:
        token_hash = hash_token(refresh_token)
        now = self._clock.now()

        async with self._uow_factory(None) as uow:
            session = await uow.sessions.get_by_refresh_token_hash(token_hash)
            if session is None or session.revoked_at is not None:
                return
            session.revoked_at = now
            await uow.sessions.update(session)
