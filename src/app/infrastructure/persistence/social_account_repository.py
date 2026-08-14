"""Implements
``app.services.ports.social_account_repository.SocialAccountRepository``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.social_account import SocialAccount
from app.infrastructure.persistence.mapping import social_accounts_table
from app.shared.ids import SocialAccountId, TenantId


class SqlSocialAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, account_id: SocialAccountId) -> SocialAccount | None:
        stmt = select(SocialAccount).where(
            social_accounts_table.c.tenant_id == tenant_id,
            social_accounts_table.c.id == account_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, account: SocialAccount) -> None:
        self._session.add(account)
        await self._session.flush()
