"""Secrets must not survive the log formatter.

This is a security control, not a formatting nicety — see CLAUDE.md §11. The
tests below are deliberately hostile: nesting, lists, mixed case, and the
specific field names this system will actually hold credentials under.
"""

from __future__ import annotations

import pytest

from app.infrastructure.observability.logging import (
    REDACTED,
    SENSITIVE_KEY_PARTS,
    redact_processor,
)


def redact(event: dict[str, object]) -> dict[str, object]:
    return dict(redact_processor(None, "info", event))  # type: ignore[arg-type]


@pytest.mark.parametrize("key", SENSITIVE_KEY_PARTS)
def test_every_declared_sensitive_key_is_redacted(key: str) -> None:
    assert redact({key: "hunter2"})[key] == REDACTED


@pytest.mark.parametrize(
    "key",
    [
        "access_token",
        "refresh_token",
        "Authorization",
        "CLIENT_SECRET",
        "instagram_access_token",
        "credentials_encrypted",
        "db_password",
        "X-Api-Key",
        "sentry_dsn",
    ],
)
def test_realistic_field_names_are_redacted(key: str) -> None:
    """The names this codebase will genuinely put credentials under."""
    assert redact({key: "sensitive"})[key] == REDACTED


def test_redaction_reaches_nested_structures() -> None:
    event = {
        "event": "channel_connected",
        "account": {
            "provider": "instagram",
            "access_token": "IGQVJ...",
            "nested": {"client_secret": "abc"},
        },
        "history": [
            {"token": "one"},
            {"token": "two"},
        ],
    }

    result = redact(event)

    account = result["account"]
    assert isinstance(account, dict)
    assert account["access_token"] == REDACTED
    assert account["nested"]["client_secret"] == REDACTED
    # Non-sensitive siblings survive, or the logs become useless.
    assert account["provider"] == "instagram"

    history = result["history"]
    assert isinstance(history, list)
    assert [entry["token"] for entry in history] == [REDACTED, REDACTED]


def test_ordinary_fields_are_untouched() -> None:
    event = {
        "event": "product_created",
        "product_id": "p01",
        "price_amount": 185000,
        "tags": ["silk", "bridal"],
    }
    assert redact(event) == event


def test_strings_are_not_treated_as_sequences() -> None:
    """A str is a Sequence; iterating it would explode into a list of chars."""
    assert redact({"event": "hello"})["event"] == "hello"


def test_deeply_recursive_structure_terminates() -> None:
    """A cyclic-looking structure must not hang the logger."""
    deep: dict[str, object] = {"token": "leaf"}
    for _ in range(50):
        deep = {"nested": deep}

    result = redact(deep)

    assert result  # returned rather than recursed forever


@pytest.mark.parametrize(
    "key",
    ["api_key", "api-key", "apiKey", "X-Api-Key", "API KEY", "x.api.key"],
)
def test_separator_and_case_variants_all_match(key: str) -> None:
    """Header-style hyphenated names are the easy ones to miss."""
    assert redact({key: "sensitive"})[key] == REDACTED
