"""The SQL implementation of the ``UnitOfWork`` port.

The one thing this module exists for: **``SET LOCAL`` the tenant, inside the
transaction, before any tenant-scoped statement runs (D3).**

Two details that are easy to get wrong and would silently defeat isolation:

- ``SET LOCAL app.current_tenant = 'xxx'`` cannot be parameterised — Postgres
  does not accept placeholders inside a bare ``SET`` statement. The
  parameterisable equivalent is ``select set_config(name, value, is_local)``,
  which is what this module uses.
- When no tenant is bound, ``current_setting(..., true)`` reads back as NULL
  on a connection that has never touched the GUC, or as an empty string on
  one that set it in an earlier transaction (Postgres, not this code — see
  ``migrations/rls.py``). Every RLS policy predicate normalises both with
  ``NULLIF(..., '')`` before comparing, so an unset tenant context reads as
  zero rows either way rather than a database error on a reused pooled
  connection.
"""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.shared.ids import TenantId

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tenant_id, true)")


class SqlUnitOfWork:
    """Implements ``app.services.ports.unit_of_work.UnitOfWork``.

    Not declared as inheriting the ``Protocol`` — structural typing means this
    satisfies the port by shape, per the pattern in CLAUDE.md §14.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        tenant_id: TenantId | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._tenant_id = tenant_id
        self._session: AsyncSession | None = None

    @property
    def session(self) -> AsyncSession:
        """Only for adapters constructed by ``bootstrap``, which knows the
        concrete SQL implementation is in play. Ports never expose this."""
        if self._session is None:
            raise RuntimeError("SqlUnitOfWork used outside its `async with` block")
        return self._session

    async def __aenter__(self) -> SqlUnitOfWork:
        session = self._session_factory()
        await session.begin()
        if self._tenant_id is not None:
            await session.execute(_SET_TENANT, {"tenant_id": str(self._tenant_id)})
        self._session = session
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self.session  # raises if __aenter__ was never called
        try:
            if exc_type is None:
                await session.commit()
            else:
                await session.rollback()
        finally:
            await session.close()
            self._session = None


def make_unit_of_work_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[TenantId | None], SqlUnitOfWork]:
    """Satisfies ``UnitOfWorkFactory``. A named function rather than a
    ``lambda`` bound inline in ``bootstrap``, so it appears in a traceback
    with an intention-revealing name.
    """

    def factory(tenant_id: TenantId | None = None) -> SqlUnitOfWork:
        return SqlUnitOfWork(session_factory, tenant_id)

    return factory
