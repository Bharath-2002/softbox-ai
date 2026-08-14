"""A connected external channel account (D21/D22) — one row per
provider-linked account a tenant has authorised for publishing.

`status` ships with a single member, `CONNECTED`, matching the reasoning
in `migrations/versions/2daa149ded1f_add_social_accounts.py`: nothing in
this storage-layer chunk drives a transition, so there is nothing to
validate a wider vocabulary against yet. The not-yet-built OAuth-connect
chunk widens it via an expand migration once it has a real state machine
(token expiry, revocation, error) to encode.

`credentials_encrypted`/`encryption_key_id` are `None` on every row
`create()` produces today — this chunk has no encryption adapter to
populate them with. A future connect/rotate flow sets both together, never
one without the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.shared.ids import SocialAccountId, TenantId, new_social_account_id


class SocialAccountStatus(StrEnum):
    CONNECTED = "connected"


@dataclass
class SocialAccount:
    id: SocialAccountId
    tenant_id: TenantId
    provider: str
    external_account_id: str
    display_name: str
    credentials_encrypted: bytes | None
    encryption_key_id: str | None
    scopes: list[str]
    access_expires_at: datetime | None
    refresh_expires_at: datetime | None
    status: SocialAccountStatus
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        *,
        provider: str,
        external_account_id: str,
        display_name: str,
        scopes: list[str] | None = None,
        now: datetime,
    ) -> SocialAccount:
        return SocialAccount(
            id=new_social_account_id(),
            tenant_id=tenant_id,
            provider=provider,
            external_account_id=external_account_id,
            display_name=display_name,
            credentials_encrypted=None,
            encryption_key_id=None,
            scopes=scopes if scopes is not None else [],
            access_expires_at=None,
            refresh_expires_at=None,
            status=SocialAccountStatus.CONNECTED,
            last_error=None,
            created_at=now,
            updated_at=now,
        )
