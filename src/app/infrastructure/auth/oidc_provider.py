"""Implements ``app.services.ports.identity_provider.IdentityProvider`` with Authlib.

Uses the low-level primitives Authlib composes for its Starlette/Flask
integrations (``create_authorization_url``, ``fetch_access_token``,
``parse_id_token``) directly, deliberately bypassing the
``request.session``-based convenience wrappers (``authorize_redirect``,
``authorize_access_token``) — this project keeps state/nonce handling
explicit in the login feature rather than delegated to a framework session,
so only the primitives are needed. ``parse_id_token`` is where the real work
happens: it fetches the provider's JWKS, verifies the ID token's signature
against it, and checks issuer, audience, expiry and nonce - all Authlib's
tested code, not hand-rolled here. Getting JWT signature verification wrong
is a classic, serious vulnerability class; the point of this adapter is to
not be the place that reimplements it.
"""

from __future__ import annotations

from authlib.integrations.starlette_client import OAuth

from app.services.ports.identity_provider import OidcClaims
from app.shared.errors import AuthenticationError


class AuthlibIdentityProvider:
    def __init__(
        self,
        *,
        provider_name: str,
        client_id: str,
        client_secret: str,
        server_metadata_url: str,
        scope: str = "openid email profile",
    ) -> None:
        self.provider_name = provider_name
        oauth = OAuth()
        self._client = oauth.register(
            name=provider_name,
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url=server_metadata_url,
            client_kwargs={"scope": scope},
        )

    async def build_authorization_url(self, *, redirect_uri: str, state: str, nonce: str) -> str:
        result = await self._client.create_authorization_url(
            redirect_uri=redirect_uri, state=state, nonce=nonce
        )
        return str(result["url"])

    async def exchange_code(self, *, code: str, redirect_uri: str, nonce: str) -> OidcClaims:
        try:
            token = await self._client.fetch_access_token(redirect_uri=redirect_uri, code=code)
            userinfo = await self._client.parse_id_token(token, nonce=nonce)
        except Exception as exc:
            # Every Authlib failure here - bad code, forged signature, nonce
            # mismatch, expired token - collapses to one outcome: this
            # exchange cannot be trusted. The caller does not need to
            # distinguish why; distinguishing risks leaking which check
            # failed to whoever is attempting the exchange.
            raise AuthenticationError("Could not verify identity provider response.") from exc

        metadata = await self._client.load_server_metadata()
        return OidcClaims(
            subject=str(userinfo["sub"]),
            issuer=str(metadata["issuer"]),
            email=userinfo.get("email"),
            email_verified=bool(userinfo.get("email_verified", False)),
            name=userinfo.get("name"),
            raw=dict(userinfo),
        )
