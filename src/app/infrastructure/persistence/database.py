"""Engine and session construction.

Takes a plain DSN string, never a ``Settings`` object — infrastructure adapters
are constructed from primitive config values so they stay usable in a test with
no environment, and so infrastructure never imports the composition root
(enforced by the ``infra_does_not_import_bootstrap`` contract).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(
    dsn: str,
    *,
    echo: bool = False,
    pool_size: int = 10,
    max_overflow: int = 5,
) -> AsyncEngine:
    return create_async_engine(
        dsn,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        # A stale connection is worse than a slightly slower one: check it out
        # with a lightweight ping and reconnect rather than surfacing a
        # confusing mid-request failure from a connection Postgres closed hours
        # ago.
        pool_pre_ping=True,
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        # Entities stay usable after commit — a use case that returns an
        # entity for the API layer to serialise should not trigger a lazy
        # reload (which would fail anyway under D7's lazy="raise").
        expire_on_commit=False,
    )


async def ping(engine: AsyncEngine) -> None:
    """Cheapest possible liveness probe, for the /ready check."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
