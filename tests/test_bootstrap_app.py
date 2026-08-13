"""``create_app``'s email-backend wiring (CHECKLIST.md, email chunk).

Not a route-level test — nothing depends on ``app.state.email_sender``
through HTTP yet — but the branch itself (which concrete adapter gets
attached) is real production wiring and needs its own test independent of
any future consumer, the same reasoning ``test_openapi.py`` applied to the
``docs_url``/``openapi_url`` branch.
"""

from __future__ import annotations

from app.bootstrap.app import create_app
from app.bootstrap.settings import Settings
from app.infrastructure.email.console_sender import ConsoleEmailSender
from app.infrastructure.email.smtp_sender import SmtpEmailSender


def test_console_is_the_default_email_backend() -> None:
    app = create_app(Settings(environment="test", log_format="console"))

    assert isinstance(app.state.email_sender, ConsoleEmailSender)


def test_smtp_backend_is_configured_from_settings() -> None:
    app = create_app(
        Settings(
            environment="test",
            log_format="console",
            email_backend="smtp",
            smtp_host="smtp.example.com",
            smtp_port=2525,
            smtp_user="user@example.com",
            smtp_password="an-app-password",
            email_from="Softbox AI <no-reply@example.com>",
        )
    )

    sender = app.state.email_sender
    assert isinstance(sender, SmtpEmailSender)
    assert sender._host == "smtp.example.com"
    assert sender._port == 2525
    assert sender._username == "user@example.com"
    assert sender._password == "an-app-password"
    assert sender._sender == "Softbox AI <no-reply@example.com>"
    assert sender._use_tls is True
