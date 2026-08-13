from __future__ import annotations

from app.entities.identity import Identity


class InMemoryIdentityRepository:
    def __init__(self) -> None:
        # Keyed by the real uniqueness constraint, not by id - a fake keyed
        # by id alone would silently permit two identities for one
        # (provider, issuer, subject), which the real schema forbids.
        self._rows: dict[tuple[str, str, str], Identity] = {}

    async def get_by_provider_subject(
        self, provider: str, issuer: str, subject: str
    ) -> Identity | None:
        return self._rows.get((provider, issuer, subject))

    async def add(self, identity: Identity) -> None:
        self._rows[(identity.provider, identity.issuer, identity.subject)] = identity
