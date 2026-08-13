"""AccessTokenCodec — no database needed, pure crypto/claims logic."""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.errors import AuthenticationError

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"


def _codec(ttl: timedelta = timedelta(minutes=15)) -> AccessTokenCodec:
    return AccessTokenCodec(SIGNING_KEY, ttl=ttl)


def _claims(**overrides: object) -> AccessTokenClaims:
    defaults: dict[str, object] = {
        "subject": "user-1",
        "tenant_id": "tenant-1",
        "role": "admin",
        "capabilities": ["catalog.publish"],
        "is_platform_admin": False,
    }
    defaults.update(overrides)
    return AccessTokenClaims(**defaults)  # type: ignore[arg-type]


def test_short_signing_key_is_rejected_at_construction() -> None:
    with pytest.raises(ValueError, match="at least 32"):
        AccessTokenCodec("too-short")


def test_encode_then_decode_round_trips() -> None:
    codec = _codec()
    now = utcnow()
    token = codec.encode(_claims(), now=now)

    decoded = codec.decode(token, now=now)

    assert decoded.subject == "user-1"
    assert decoded.tenant_id == "tenant-1"
    assert decoded.role == "admin"
    assert decoded.capabilities == ["catalog.publish"]
    assert decoded.is_platform_admin is False


def test_platform_scoped_token_has_no_tenant_or_role() -> None:
    codec = _codec()
    now = utcnow()
    token = codec.encode(
        _claims(tenant_id=None, role=None, capabilities=[], is_platform_admin=True), now=now
    )

    decoded = codec.decode(token, now=now)

    assert decoded.tenant_id is None
    assert decoded.role is None
    assert decoded.is_platform_admin is True


def test_expired_token_is_rejected() -> None:
    codec = _codec(ttl=timedelta(minutes=15))
    issued_at = utcnow()
    token = codec.encode(_claims(), now=issued_at)

    with pytest.raises(AuthenticationError):
        codec.decode(token, now=issued_at + timedelta(minutes=16))


def test_tampered_payload_is_rejected() -> None:
    codec = _codec()
    token = codec.encode(_claims(), now=utcnow())
    header, payload, signature = token.split(".")
    tampered = f"{header}.{payload}A.{signature}"  # corrupt the payload segment

    with pytest.raises(AuthenticationError):
        codec.decode(tampered, now=utcnow())


def test_token_signed_with_a_different_key_is_rejected() -> None:
    token = _codec().encode(_claims(), now=utcnow())
    other_codec = AccessTokenCodec("a-completely-different-signing-secret-value")

    with pytest.raises(AuthenticationError):
        other_codec.decode(token, now=utcnow())


def test_garbage_input_is_rejected_not_raised_as_an_unhandled_exception() -> None:
    with pytest.raises(AuthenticationError):
        _codec().decode("not-a-jwt-at-all", now=utcnow())
