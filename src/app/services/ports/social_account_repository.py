"""Port for `social_accounts` (D21/D22). `get`/`add` only — nothing in
this storage-layer chunk mutates a row after creation, so no `update`
yet, matching the "add the mutation exactly when a real caller needs it"
discipline `GenerationRequestRepository` already established.
"""

from __future__ import annotations

from typing import Protocol

from app.entities.social_account import SocialAccount
from app.shared.ids import SocialAccountId, TenantId


class SocialAccountRepository(Protocol):
    async def get(
        self, tenant_id: TenantId, account_id: SocialAccountId
    ) -> SocialAccount | None: ...

    async def add(self, account: SocialAccount) -> None: ...
