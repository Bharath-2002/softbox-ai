"""Links between a ``User`` and an external identity provider."""

from __future__ import annotations

from typing import Protocol

from app.entities.identity import Identity


class IdentityRepository(Protocol):
    async def get_by_provider_subject(
        self, provider: str, issuer: str, subject: str
    ) -> Identity | None:
        """The login lookup: given verified OIDC claims, is there already a
        user for this ``(provider, issuer, subject)``? ``subject`` alone is
        not enough — the OIDC ``sub`` claim is only unique within one issuer."""
        ...

    async def add(self, identity: Identity) -> None: ...
