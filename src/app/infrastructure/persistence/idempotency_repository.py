"""Implements ``app.services.ports.idempotency_repository.IdempotencyRepository``.

Core queries against ``idempotency_keys_table`` directly — there is no rich
entity to hydrate, same shape as ``SqlPlatformAdminRepository``.

``reserve`` uses ``INSERT ... ON CONFLICT DO NOTHING ... RETURNING`` rather
than checking ``rowcount``: a conflicting insert returns no row, so
``scalar_one_or_none() is not None`` is an unambiguous "did this call win
the race" regardless of driver-level rowcount reporting quirks.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.persistence.mapping import idempotency_keys_table
from app.services.ports.idempotency_repository import IdempotencyRecord
from app.shared.ids import TenantId


class SqlIdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, tenant_id: TenantId, key: str) -> IdempotencyRecord | None:
        stmt = select(
            idempotency_keys_table.c.key,
            idempotency_keys_table.c.request_fingerprint,
            idempotency_keys_table.c.response_status,
            idempotency_keys_table.c.response_body,
            idempotency_keys_table.c.created_at,
        ).where(
            idempotency_keys_table.c.tenant_id == tenant_id,
            idempotency_keys_table.c.key == key,
        )
        row = (await self._session.execute(stmt)).one_or_none()
        if row is None:
            return None
        return IdempotencyRecord(
            key=row.key,
            request_fingerprint=row.request_fingerprint,
            response_status=row.response_status,
            response_body=row.response_body,
            created_at=row.created_at,
        )

    async def reserve(
        self, tenant_id: TenantId, key: str, *, request_fingerprint: str, now: datetime
    ) -> bool:
        stmt = (
            insert(idempotency_keys_table)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                key=key,
                request_fingerprint=request_fingerprint,
                response_status=None,
                response_body=None,
                created_at=now,
            )
            .on_conflict_do_nothing(
                index_elements=[idempotency_keys_table.c.tenant_id, idempotency_keys_table.c.key]
            )
            .returning(idempotency_keys_table.c.id)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.scalar_one_or_none() is not None

    async def store_response(
        self, tenant_id: TenantId, key: str, *, status: int, body: dict[str, Any] | None
    ) -> None:
        stmt = (
            idempotency_keys_table.update()
            .where(
                idempotency_keys_table.c.tenant_id == tenant_id,
                idempotency_keys_table.c.key == key,
            )
            .values(response_status=status, response_body=body)
        )
        await self._session.execute(stmt)
        await self._session.flush()
