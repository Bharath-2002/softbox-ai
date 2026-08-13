from __future__ import annotations

from datetime import datetime, timedelta

from app.shared.clock import fixed_window_start
from app.shared.ids import TenantId


class InMemoryRateLimiter:
    def __init__(self) -> None:
        self._counts: dict[tuple[TenantId, str, datetime], int] = {}

    async def allow(
        self, tenant_id: TenantId, bucket: str, *, limit: int, window: timedelta, now: datetime
    ) -> bool:
        window_start = fixed_window_start(now, window)
        key = (tenant_id, bucket, window_start)
        count = self._counts.get(key, 0)
        if count >= limit:
            return False
        self._counts[key] = count + 1
        return True
