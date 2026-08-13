"""The one primitive every tenant-scoped adapter must run before a
tenant-scoped statement (D3): ``SET LOCAL app.current_tenant``,
parameterised via ``set_config`` because Postgres does not accept
placeholders inside a bare ``SET``.

Shared by ``SqlUnitOfWork.__aenter__`` and any adapter whose lifecycle is
per-call rather than per-transaction (``SqlRateLimiter``) — the statement
text has exactly one place to be right, rather than two copies that could
quietly drift apart.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.ids import TenantId

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")


async def bind_tenant(session: AsyncSession, tenant_id: TenantId) -> None:
    await session.execute(_SET_TENANT, {"tenant_id": str(tenant_id)})
