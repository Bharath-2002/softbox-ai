from __future__ import annotations

from app.entities.social_account import SocialAccount
from app.shared.ids import SocialAccountId, TenantId


class InMemorySocialAccountRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, SocialAccountId], SocialAccount] = {}

    async def get(self, tenant_id: TenantId, account_id: SocialAccountId) -> SocialAccount | None:
        return self._rows.get((tenant_id, account_id))

    async def add(self, account: SocialAccount) -> None:
        self._rows[(account.tenant_id, account.id)] = account
