"""Implements ``app.services.ports.rate_limiter.RateLimiter``.

Opens and commits its own short-lived session per call rather than
participating in a use case's ``UnitOfWork`` — see the port's module
docstring for why. Still binds ``app.current_tenant`` via
``tenant_scope.bind_tenant`` first, since ``rate_limit_windows`` is
RLS-forced (D3) exactly like every other tenant-scoped table.

Fixed windows are aligned to the Unix epoch, not to each call's own
timestamp — ``floor(now / window) * window`` — so that two calls landing in
the same wall-clock window always compute the same ``window_start`` and
therefore hit the same row, regardless of which one happens to run first.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.persistence.mapping import rate_limit_windows_table
from app.infrastructure.persistence.tenant_scope import bind_tenant
from app.shared.clock import fixed_window_start
from app.shared.ids import TenantId


class SqlRateLimiter:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def allow(
        self, tenant_id: TenantId, bucket: str, *, limit: int, window: timedelta, now: datetime
    ) -> bool:
        window_start = fixed_window_start(now, window)
        async with self._session_factory() as session:
            await session.begin()
            await bind_tenant(session, tenant_id)
            stmt = (
                insert(rate_limit_windows_table)
                .values(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    bucket=bucket,
                    window_start=window_start,
                    count=1,
                )
                .on_conflict_do_update(
                    index_elements=[
                        rate_limit_windows_table.c.tenant_id,
                        rate_limit_windows_table.c.bucket,
                        rate_limit_windows_table.c.window_start,
                    ],
                    set_={"count": rate_limit_windows_table.c.count + 1},
                    where=rate_limit_windows_table.c.count < limit,
                )
                .returning(rate_limit_windows_table.c.count)
            )
            result = await session.execute(stmt)
            allowed = result.scalar_one_or_none() is not None
            await session.commit()
            return allowed
