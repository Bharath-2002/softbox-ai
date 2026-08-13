"""A person's identity, independent of any tenant.

The same user can belong to several tenants (D4's tenant/platform plane
split) — this is why ``User`` carries no ``tenant_id`` and why it is not
RLS-protected in the schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.shared.ids import UserId, new_user_id


class UserStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


@dataclass
class User:
    id: UserId
    email: str
    email_verified: bool
    display_name: str | None
    status: UserStatus
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def register(email: str, *, now: datetime, display_name: str | None = None) -> User:
        """A new user, from a first successful login. Email is always stored
        lowercased — the uniqueness index is on ``lower(email)``, so a mixed
        case value here would only be confusing, never actually permitted to
        collide."""
        return User(
            id=new_user_id(),
            email=email.strip().lower(),
            email_verified=False,
            display_name=display_name,
            status=UserStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
