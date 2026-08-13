"""The platform plane guard (D4).

Deliberately its own tiny port rather than folded into ``UserRepository`` —
"is this user a platform admin" is a distinct, security-sensitive question
asked from the authorization path, not an ordinary user lookup.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.shared.ids import UserId


class PlatformAdminRepository(Protocol):
    async def is_admin(self, user_id: UserId) -> bool: ...

    async def grant(self, user_id: UserId, *, granted_by: UserId, now: datetime) -> None: ...
