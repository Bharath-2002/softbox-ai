from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.ports.idempotency_repository import IdempotencyRecord
from app.shared.ids import TenantId


class InMemoryIdempotencyRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, str], IdempotencyRecord] = {}

    async def get(self, tenant_id: TenantId, key: str) -> IdempotencyRecord | None:
        return self._rows.get((tenant_id, key))

    async def reserve(
        self, tenant_id: TenantId, key: str, *, request_fingerprint: str, now: datetime
    ) -> bool:
        if (tenant_id, key) in self._rows:
            return False
        self._rows[(tenant_id, key)] = IdempotencyRecord(
            key=key,
            request_fingerprint=request_fingerprint,
            response_status=None,
            response_body=None,
            created_at=now,
        )
        return True

    async def store_response(
        self, tenant_id: TenantId, key: str, *, status: int, body: dict[str, Any] | None
    ) -> None:
        existing = self._rows[(tenant_id, key)]
        self._rows[(tenant_id, key)] = IdempotencyRecord(
            key=existing.key,
            request_fingerprint=existing.request_fingerprint,
            response_status=status,
            response_body=body,
            created_at=existing.created_at,
        )
