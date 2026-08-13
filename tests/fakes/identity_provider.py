from __future__ import annotations

from app.services.ports.identity_provider import OidcClaims
from app.shared.errors import AuthenticationError


class FakeIdentityProvider:
    """Canned claims by authorization code — no network, no real IdP.

    Session/login logic is fully tested against this; the real Authlib
    adapter gets its own narrower contract test
    (``tests/infrastructure/test_oidc_provider_contract.py``) proving it
    parses a known-good ID token, since that is the one thing this fake
    cannot stand in for.
    """

    def __init__(self, provider_name: str = "fake") -> None:
        self.provider_name = provider_name
        self._claims_by_code: dict[str, OidcClaims] = {}
        self.built_urls: list[dict[str, str]] = []

    def register_code(self, code: str, claims: OidcClaims) -> None:
        self._claims_by_code[code] = claims

    async def build_authorization_url(self, *, redirect_uri: str, state: str, nonce: str) -> str:
        self.built_urls.append({"redirect_uri": redirect_uri, "state": state, "nonce": nonce})
        return f"https://fake.example.com/authorize?state={state}&nonce={nonce}"

    async def exchange_code(self, *, code: str, redirect_uri: str, nonce: str) -> OidcClaims:
        claims = self._claims_by_code.get(code)
        if claims is None:
            raise AuthenticationError("Invalid authorization code.")
        return claims
