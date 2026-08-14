"""Abuse / NSFW scanning on ingest (D17, M3 Gate). No real adapter exists
yet — no moderation provider credentials are configured anywhere in this
repo (see CHECKLIST.md's M3 STATE entry). Only a fake exists, used by tests
and, until a provider is chosen, nowhere else — the same "port built ahead
of its adapter" shape ``EmailSender`` used before SMTP credentials existed,
except here the adapter side is the piece still missing, not just unused.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ModerationVerdict:
    is_safe: bool
    reason: str | None = None


class ContentModerationScanner(Protocol):
    async def scan(self, data: bytes, *, mime: str) -> ModerationVerdict: ...
