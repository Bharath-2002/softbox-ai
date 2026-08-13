"""Implements ``app.services.ports.email_sender.EmailSender`` over SMTP.

``aiosmtplib``, not the stdlib ``smtplib`` — this codebase is async
end to end, and a blocking SMTP call inside an ``async def`` would stall the
event loop for every other in-flight request for the duration of the
connection and send.

``use_tls`` defaults to ``True`` (STARTTLS) — a plaintext SMTP submission
carrying an app password is exactly the credential leak CLAUDE.md §11 exists
to prevent, so real construction (``bootstrap``) never turns it off. The
knob exists only so the offline contract test can point this exact adapter
at a local, unencrypted ``aiosmtpd`` test server without a throwaway TLS
certificate — a test-only need, not a production configuration surface.
"""

from __future__ import annotations

from email.message import EmailMessage as MimeEmailMessage

import aiosmtplib

from app.services.ports.email_sender import EmailMessage


class SmtpEmailSender:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        sender: str,
        use_tls: bool = True,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._sender = sender
        self._use_tls = use_tls

    async def send(self, message: EmailMessage) -> None:
        mime = MimeEmailMessage()
        mime["From"] = self._sender
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body_text)
        if message.body_html is not None:
            mime.add_alternative(message.body_html, subtype="html")

        await aiosmtplib.send(
            mime,
            hostname=self._host,
            port=self._port,
            username=self._username or None,
            password=self._password or None,
            start_tls=self._use_tls,
        )
