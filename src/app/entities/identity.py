"""A credential linking a ``User`` to one external identity provider.

Uniqueness is ``(provider, issuer, subject)`` — the OIDC ``sub`` claim is only
guaranteed unique *within one issuer*. Comparing subject alone would collide
the moment a second issuer for the same provider exists (two Entra tenants,
for instance).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.shared.ids import IdentityId, UserId, new_identity_id


@dataclass
class Identity:
    id: IdentityId
    user_id: UserId
    provider: str
    issuer: str
    subject: str
    raw_claims: dict[str, Any]
    created_at: datetime

    @staticmethod
    def create(
        user_id: UserId,
        *,
        provider: str,
        issuer: str,
        subject: str,
        raw_claims: dict[str, Any],
        now: datetime,
    ) -> Identity:
        return Identity(
            id=new_identity_id(),
            user_id=user_id,
            provider=provider,
            issuer=issuer,
            subject=subject,
            raw_claims=raw_claims,
            created_at=now,
        )
