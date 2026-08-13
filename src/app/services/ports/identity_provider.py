"""An OIDC identity provider (D4) — Google Workspace, Entra, or any other.

The port carries no Authlib types in its signature (no session, no client, no
JWKS) — only plain data, per the port-writing rule in CLAUDE.md §14: a port
names a capability, never a technology.

State (CSRF) is deliberately not this port's concern — it is a plain string
comparison the caller (the login/callback feature) owns, generated and
checked server-side around the redirect round-trip. ``nonce`` **is** this
port's concern, because verifying it is embedded correctly in the returned
ID token is part of what makes ``exchange_code`` trustworthy, not a separate
step a caller could forget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class OidcClaims:
    """Verified claims from a provider's ID token.

    ``subject`` is unique only within ``issuer`` — never compare subjects
    across providers or issuers without both (see ``IdentityRepository`` and
    the identities migration).
    """

    subject: str
    issuer: str
    email: str | None
    email_verified: bool
    name: str | None
    raw: dict[str, Any]


class IdentityProvider(Protocol):
    provider_name: str

    async def build_authorization_url(self, *, redirect_uri: str, state: str, nonce: str) -> str:
        """The URL to send the user's browser to. ``state`` and ``nonce`` are
        generated and stored by the caller, not this port."""
        ...

    async def exchange_code(self, *, code: str, redirect_uri: str, nonce: str) -> OidcClaims:
        """Redeems an authorization code for verified claims: signature
        checked against the provider's published keys, issuer and audience
        checked, and ``nonce`` checked against what the caller generated
        before the redirect. Raises ``AuthenticationError`` (``app.shared.errors``)
        on any verification failure — a caller never receives claims it
        cannot trust."""
        ...
