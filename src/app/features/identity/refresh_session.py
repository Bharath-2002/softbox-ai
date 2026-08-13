"""Rotates a refresh token and mints a new access token (D4).

Rotation with reuse detection: the token presented is looked up first as the
session's *current* hash (the normal case), and if that fails, as its
*previous* hash. A hit on the previous hash means this exact token was
already rotated away — it is being replayed, either by a client racing its
own rotation or by whoever stole it — and the response is the same either
way: the entire session is revoked, not just this one call rejected. A
narrower response would let a genuine attacker keep trying with the same
stolen token indefinitely.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.ports.token_issuer import AccessTokenClaims, TokenIssuer
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.principal_resolver import PrincipalResolver
from app.shared.clock import Clock
from app.shared.errors import AuthenticationError
from app.shared.tokens import generate_token, hash_token


@dataclass(frozen=True)
class RefreshResult:
    access_token: str
    refresh_token: str


class RefreshSession:
    def __init__(
        self,
        token_issuer: TokenIssuer,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
    ) -> None:
        self._token_issuer = token_issuer
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, refresh_token: str) -> RefreshResult:
        presented_hash = hash_token(refresh_token)
        now = self._clock.now()

        async with self._uow_factory(None) as uow:
            session = await uow.sessions.get_by_refresh_token_hash(presented_hash)

            if session is None:
                reused = await uow.sessions.get_by_previous_token_hash(presented_hash)
                if reused is not None:
                    await uow.sessions.revoke_all_for_user(reused.user_id, now=now)
                raise AuthenticationError("Invalid refresh token.")

            if not session.is_active(now=now):
                raise AuthenticationError("Session is no longer active.")

            new_refresh_token = generate_token()
            session.previous_token_hash = session.refresh_token_hash
            session.refresh_token_hash = hash_token(new_refresh_token)
            await uow.sessions.update(session)

            principal = await PrincipalResolver(
                uow.tenant_memberships, uow.platform_admins
            ).resolve(session.user_id, session.tenant_id)

        access_token = self._token_issuer.encode(
            AccessTokenClaims(
                subject=str(session.user_id),
                tenant_id=str(session.tenant_id) if session.tenant_id else None,
                role=principal.role.value if principal.role else None,
                capabilities=sorted(principal.capabilities),
                is_platform_admin=principal.is_platform_admin,
            ),
            now=now,
        )
        return RefreshResult(access_token=access_token, refresh_token=new_refresh_token)
