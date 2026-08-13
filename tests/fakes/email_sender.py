from __future__ import annotations

from app.services.ports.email_sender import EmailMessage


class FakeEmailSender:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def send(self, message: EmailMessage) -> None:
        self.sent.append(message)
