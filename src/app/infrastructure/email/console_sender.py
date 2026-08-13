"""Implements ``EmailSender`` by logging instead of sending.

The default backend (`SOFTBOX_EMAIL_BACKEND=console`) — local development
and CI have no real SMTP credentials, and `.env.example`'s placeholder
`SMTP_PASSWORD` is not one. Logging the message (never its full body, to
keep verification-code-style content off disk) lets a developer confirm an
email *would* have been sent without an outbound network dependency.
"""

from __future__ import annotations

from app.services.ports.email_sender import EmailMessage
from app.shared.logging import get_logger

_log = get_logger(__name__)


class ConsoleEmailSender:
    async def send(self, message: EmailMessage) -> None:
        _log.info("email_not_sent_console_backend", to=message.to, subject=message.subject)
