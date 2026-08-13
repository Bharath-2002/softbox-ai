"""The one test in this codebase that talks to real Authlib code for ID token
verification, rather than the fake (``tests/fakes/identity_provider.py``).

No network call: a self-signed RSA keypair stands in for a provider's JWKS,
injected directly into the adapter's cached server metadata so
``load_server_metadata`` never fetches anything, and only
``fetch_access_token`` (the token-endpoint HTTP call) is patched out. Every
other step - ``parse_id_token``'s signature verification against the JWKS,
issuer/audience/nonce checking - runs for real. Verified by hand before
writing this (see the chunk's dev notes): a forged signature and a nonce
mismatch are both rejected by this exact setup, not just a valid token
accepted.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from joserfc import jwt as rfc_jwt
from joserfc.jwk import RSAKey

from app.infrastructure.auth.oidc_provider import AuthlibIdentityProvider
from app.shared.errors import AuthenticationError

CLIENT_ID = "test-client-id"
ISSUER = "https://issuer.example.com"
KEY_ID = "test-key-1"


def _provider_with_token(id_token: str, key: RSAKey) -> AuthlibIdentityProvider:
    provider = AuthlibIdentityProvider(
        provider_name="test",
        client_id=CLIENT_ID,
        client_secret="unused-in-this-flow",
        server_metadata_url="https://issuer.example.com/.well-known/openid-configuration",
    )
    # Pre-populate what load_server_metadata would otherwise fetch over
    # HTTPS, so parse_id_token's real verification runs against it directly.
    metadata = provider._client.server_metadata
    metadata["issuer"] = ISSUER
    metadata["jwks"] = {"keys": [key.as_dict(private=False)]}
    metadata["_loaded_at"] = time.time()

    # Only the token-endpoint HTTP call is faked - the genuinely network-bound
    # step. parse_id_token and load_server_metadata are untouched.
    async def fake_fetch_access_token(**_kwargs: Any) -> dict[str, str]:
        return {"id_token": id_token}

    provider._client.fetch_access_token = fake_fetch_access_token
    return provider


def _sign(claims: dict[str, object], key: RSAKey) -> str:
    return rfc_jwt.encode({"alg": "RS256", "kid": KEY_ID}, claims, key)


def _base_claims(**overrides: object) -> dict[str, object]:
    now = int(time.time())
    claims: dict[str, object] = {
        "iss": ISSUER,
        "sub": "provider-subject-123",
        "aud": CLIENT_ID,
        "exp": now + 300,
        "iat": now,
        "nonce": "expected-nonce",
        "email": "person@example.com",
        "email_verified": True,
        "name": "Person Example",
    }
    claims.update(overrides)
    return claims


async def test_a_known_good_id_token_is_accepted_and_mapped_to_oidc_claims() -> None:
    key = RSAKey.generate_key(2048, parameters={"kid": KEY_ID}, private=True)
    token = _sign(_base_claims(), key)
    provider = _provider_with_token(token, key)

    claims = await provider.exchange_code(
        code="unused", redirect_uri="https://app.example.com/callback", nonce="expected-nonce"
    )

    assert claims.subject == "provider-subject-123"
    assert claims.issuer == ISSUER
    assert claims.email == "person@example.com"
    assert claims.email_verified is True
    assert claims.name == "Person Example"


async def test_a_token_signed_by_the_wrong_key_is_rejected() -> None:
    real_key = RSAKey.generate_key(2048, parameters={"kid": KEY_ID}, private=True)
    forged_key = RSAKey.generate_key(2048, parameters={"kid": KEY_ID}, private=True)
    token = _sign(_base_claims(), forged_key)
    provider = _provider_with_token(token, real_key)  # JWKS advertises the real key

    with pytest.raises(AuthenticationError):
        await provider.exchange_code(
            code="unused", redirect_uri="https://app.example.com/callback", nonce="expected-nonce"
        )


async def test_a_nonce_mismatch_is_rejected() -> None:
    key = RSAKey.generate_key(2048, parameters={"kid": KEY_ID}, private=True)
    token = _sign(_base_claims(nonce="a-different-nonce"), key)
    provider = _provider_with_token(token, key)

    with pytest.raises(AuthenticationError):
        await provider.exchange_code(
            code="unused", redirect_uri="https://app.example.com/callback", nonce="expected-nonce"
        )


async def test_an_expired_token_is_rejected() -> None:
    """``parse_id_token`` applies a 120s leeway by default (Authlib, not this
    adapter) - confirmed by first writing this with ``exp=now-60``, which
    passed verification because it was still inside that window. Expiring
    well beyond the leeway is what actually proves enforcement."""
    key = RSAKey.generate_key(2048, parameters={"kid": KEY_ID}, private=True)
    now = int(time.time())
    token = _sign(_base_claims(exp=now - 600, iat=now - 3600), key)
    provider = _provider_with_token(token, key)

    with pytest.raises(AuthenticationError):
        await provider.exchange_code(
            code="unused", redirect_uri="https://app.example.com/callback", nonce="expected-nonce"
        )
