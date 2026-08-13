"""Alembic environment.

Deliberately does not import ``app.bootstrap.settings`` or anything under
``app.infrastructure``: migrations run as the **owner** role, a different
credential from the app's own (non-owner) connection, and the app's Settings
type should never be able to hold the owner DSN at all — that is a property
worth keeping even though nothing currently enforces it mechanically.

``target_metadata`` is ``None``: there is no SQLAlchemy declarative registry
yet (D7 — entities are pure Python, mapped imperatively once the first
persisted entity exists in M2). Until then, migrations are hand-authored and
``alembic revision --autogenerate`` is not available. This is a deliberate,
temporary state, not an oversight.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None


def _migrations_url() -> str:
    url = os.environ.get("SOFTBOX_MIGRATIONS_DATABASE_URL")
    if url:
        return url
    # Matches scripts/bootstrap_local_db.sh's defaults — local development
    # only. Every other environment must set the env var explicitly.
    return "postgresql+asyncpg://softbox_owner:softbox_owner_dev_only@localhost:5432/softbox"


def run_migrations_offline() -> None:
    context.configure(
        url=_migrations_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _migrations_url()
    connectable = async_engine_from_config(configuration, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
