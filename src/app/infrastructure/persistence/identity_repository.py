"""Implements ``app.services.ports.identity_repository.IdentityRepository``.

Filters use ``identities_table.c.*``, not ``Identity.provider`` etc. — see
``user_repository.py`` for why.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.identity import Identity
from app.infrastructure.persistence.mapping import identities_table


class SqlIdentityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_provider_subject(
        self, provider: str, issuer: str, subject: str
    ) -> Identity | None:
        stmt = select(Identity).where(
            identities_table.c.provider == provider,
            identities_table.c.issuer == issuer,
            identities_table.c.subject == subject,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def add(self, identity: Identity) -> None:
        self._session.add(identity)
        await self._session.flush()
