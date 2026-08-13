"""Sessions carry no tenant-isolation guarantee of their own (see the
``sessions`` migration's docstring) — access is gated by possession of the
token whose hash is the lookup key, not by a tenant parameter on these
methods.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.entities.session import Session
from app.shared.ids import UserId


class SessionRepository(Protocol):
    async def add(self, session: Session) -> None: ...

    async def get_by_refresh_token_hash(self, token_hash: str) -> Session | None:
        """The normal path: this hash is the session's *current* token."""
        ...

    async def get_by_previous_token_hash(self, token_hash: str) -> Session | None:
        """The reuse-detection path: this hash was rotated away. A caller
        presenting it is either racing a legitimate rotation or replaying a
        stolen token — the feature layer decides which and revokes
        accordingly; this method only makes the row findable."""
        ...

    async def update(self, session: Session) -> None:
        """Persists rotation (a new ``refresh_token_hash``, the old one moved
        to ``previous_token_hash``) and revocation alike."""
        ...

    async def revoke_all_for_user(self, user_id: UserId, *, now: datetime) -> None:
        """ "Log out everywhere" — deliberately not tenant-scoped. A user's
        sessions across every tenant they belong to are revoked together."""
        ...
