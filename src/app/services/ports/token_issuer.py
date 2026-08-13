"""Issues and verifies our own short-lived access tokens (D4).

Kept as a separate port from ``IdentityProvider``, not a method on it: that
port verifies a *third party's* token (an OIDC provider's ID token, checked
against their published keys); this one issues and verifies **our own**,
signed with a key only we hold. Conflating the two would blur a genuinely
different trust boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class AccessTokenClaims:
    subject: str
    tenant_id: str | None
    role: str | None
    capabilities: list[str]
    is_platform_admin: bool
    # Set only on a token minted by StartImpersonation - the real platform
    # admin's user id, distinct from `subject` (the impersonated user). Never
    # set together with is_platform_admin=True: an impersonation token acts
    # with the target's own standing, not the admin's platform-wide power
    # (see StartImpersonation's module docstring).
    impersonated_by: str | None = None


class TokenIssuer(Protocol):
    def encode(self, claims: AccessTokenClaims, *, now: datetime) -> str: ...

    def decode(self, token: str, *, now: datetime) -> AccessTokenClaims:
        """Raises ``AuthenticationError`` (``app.shared.errors``) for any
        invalid, tampered or expired token — never returns partial claims."""
        ...
