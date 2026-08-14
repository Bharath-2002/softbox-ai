"""Implements ``ContentModerationScanner`` by always approving.

No moderation provider is configured anywhere in this repo (see
CHECKLIST.md's M3 STATE entry) — this exists so the upload path is
exercisable end-to-end in dev/test, the same role ``ConsoleEmailSender``
plays before SMTP credentials existed. Unlike a skipped email, an
unmoderated upload is a real safety gap, so every call logs a warning
rather than passing silently — this must not still be the configured
scanner the day this application takes real user uploads in production.
"""

from __future__ import annotations

from app.services.ports.content_moderation import ModerationVerdict
from app.shared.logging import get_logger

_log = get_logger(__name__)


class NullContentModerationScanner:
    async def scan(self, data: bytes, *, mime: str) -> ModerationVerdict:
        _log.warning("content_moderation_not_configured", mime=mime, size=len(data))
        return ModerationVerdict(is_safe=True)
