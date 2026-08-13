"""Outbound email.

No `tenant_id` here — unlike everything else in `services/ports`, sending an
email is not a tenant-scoped data operation, it is a side effect against a
third-party SMTP relay. A caller that needs a tenant-branded message builds
that into `EmailMessage.body_text`/`body_html` itself; this port only knows
how to hand a fully-composed message to a transport.

No use case calls this yet — built ahead of its first consumer (invite
emails, notifications) the same way `TokenIssuer` and `IdentityProvider`
were built in M1 chunk 4 before `CompleteLogin` existed to use them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body_text: str
    body_html: str | None = None


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...
