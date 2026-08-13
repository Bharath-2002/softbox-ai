"""Runs against both FakeEmailSender and SmtpEmailSender.

The real leg is a local, unencrypted ``aiosmtpd`` server on an
OS-assigned free port — no real network call, no real inbox, and
``.env.example``'s ``SMTP_PASSWORD`` placeholder is never touched. This is
the same shape as the OIDC contract test's offline self-signed JWKS: the
real protocol implementation runs for real, against a double that never
leaves this machine.

``send()`` returns nothing, so "did it work" is verified two different ways
per adapter (the fake's recorded list; the real server's received envelope)
rather than one shared assertion — the shared part of the contract, tested
uniformly below, is "sending a well-formed message does not raise."
"""

from __future__ import annotations

import socket
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
from aiosmtpd.controller import Controller

from app.infrastructure.email.smtp_sender import SmtpEmailSender
from app.services.ports.email_sender import EmailMessage, EmailSender
from tests.fakes.email_sender import FakeEmailSender


class _RecordingHandler:
    def __init__(self) -> None:
        self.received: list[tuple[str | None, list[str], bytes]] = []

    async def handle_DATA(self, server: Any, session: Any, envelope: Any) -> str:  # noqa: N802
        # aiosmtpd dispatches to this exact method name via introspection -
        # not a naming choice available to this code.
        self.received.append((envelope.mail_from, list(envelope.rcpt_tos), envelope.content))
        return "250 OK"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port: int = sock.getsockname()[1]
        return port


@dataclass
class Context:
    sender: EmailSender
    extra: dict[str, Any] = field(default_factory=dict)


@pytest_asyncio.fixture(params=["fake", "real"])
async def ctx(request: pytest.FixtureRequest) -> AsyncIterator[Context]:
    if request.param == "fake":
        fake = FakeEmailSender()
        yield Context(fake, {"fake": fake})
        return

    handler = _RecordingHandler()
    controller = Controller(handler, hostname="127.0.0.1", port=_free_port())
    controller.start()
    try:
        sender = SmtpEmailSender(
            host="127.0.0.1",
            port=controller.port,
            username="",
            password="",
            sender="sender@example.com",
            use_tls=False,
        )
        yield Context(sender, {"handler": handler})
    finally:
        controller.stop()


async def test_sending_a_well_formed_message_does_not_raise(ctx: Context) -> None:
    await ctx.sender.send(
        EmailMessage(to="person@example.com", subject="Welcome", body_text="Hello there.")
    )


async def test_sending_with_an_html_alternative_does_not_raise(ctx: Context) -> None:
    await ctx.sender.send(
        EmailMessage(
            to="person@example.com",
            subject="Welcome",
            body_text="Hello there.",
            body_html="<p>Hello there.</p>",
        )
    )


async def test_the_fake_records_the_full_message() -> None:
    fake = FakeEmailSender()
    message = EmailMessage(to="a@example.com", subject="Hi", body_text="Body text")

    await fake.send(message)

    assert fake.sent == [message]


async def test_the_real_adapter_actually_delivers_to_the_smtp_server() -> None:
    handler = _RecordingHandler()
    controller = Controller(handler, hostname="127.0.0.1", port=_free_port())
    controller.start()
    try:
        sender = SmtpEmailSender(
            host="127.0.0.1",
            port=controller.port,
            username="",
            password="",
            sender="sender@example.com",
            use_tls=False,
        )
        await sender.send(
            EmailMessage(to="person@example.com", subject="Real delivery", body_text="Hi there.")
        )
    finally:
        controller.stop()

    assert len(handler.received) == 1
    mail_from, rcpt_tos, content = handler.received[0]
    assert mail_from == "sender@example.com"
    assert rcpt_tos == ["person@example.com"]
    assert b"Subject: Real delivery" in content
    assert b"Hi there." in content
