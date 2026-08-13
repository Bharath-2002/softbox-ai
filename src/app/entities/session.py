"""A refresh-token-backed login session.

Deliberately carries no tenant-isolation guarantee of its own (see the
``sessions`` migration's docstring for why) — access is gated by possession
of the token whose hash is the lookup key, the same trust model a password
hash table uses. ``tenant_id`` is the session's *active* tenant and may be
absent for a platform-plane session.

``previous_token_hash`` exists for rotation reuse detection: when a refresh
token is rotated, the old hash moves here rather than being discarded. A
later request presenting that old token is then distinguishable from "an
unrelated invalid token" — it is a replay, and the session revocation it
should trigger is the feature layer's job, not this entity's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.shared.ids import SessionId, TenantId, UserId


@dataclass
class Session:
    id: SessionId
    user_id: UserId
    tenant_id: TenantId | None
    refresh_token_hash: str
    previous_token_hash: str | None
    expires_at: datetime
    revoked_at: datetime | None
    created_at: datetime

    def is_active(self, *, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now
