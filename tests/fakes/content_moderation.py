from __future__ import annotations

from app.services.ports.content_moderation import ModerationVerdict


class FakeContentModerationScanner:
    """Defaults to approving everything. A test that needs a rejection sets
    ``reject_reason`` before calling the use case under test."""

    def __init__(self) -> None:
        self.reject_reason: str | None = None
        self.scanned: list[bytes] = []

    async def scan(self, data: bytes, *, mime: str) -> ModerationVerdict:
        self.scanned.append(data)
        if self.reject_reason is not None:
            return ModerationVerdict(is_safe=False, reason=self.reject_reason)
        return ModerationVerdict(is_safe=True)
