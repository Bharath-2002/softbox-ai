"""Redeems a verified OIDC callback for a session and access token (D4).

Find-or-create is keyed on ``(provider, issuer, subject)`` first, not email —
that identity lookup is the one that must never collide across issuers (see
``IdentityRepository``). Falling back to an existing user by email only
happens the first time a *second* provider is linked for someone who already
has an account; every login after that resolves directly by identity.

The new session has no active tenant. Tenant selection is a separate concern,
not built here — this use case's job ends at "you are this verified person,"
not "you may act within this tenant."

``bootstrap_admin_emails`` (``Settings.admin_emails``) is the operator's
explicit platform-admin allowlist — checked and granted inside this same
transaction, before the returned token is issued, so an allowlisted email
gets ``is_platform_admin=True`` on the very *first* login rather than
needing a second one (the existing manually-granted-admin test needs two
logins because the grant happens *between* them; this path grants before
the first token is ever issued). An explicit, operator-configured list, not
domain inference — consistent with D4's "explicit grant, never inferred"
applied to platform-admin status itself. Comparison is case-insensitive,
matching how ``email`` is looked up everywhere else in this module.

``bootstrap_owner_email``/``bootstrap_owner_tenant_id`` is the same
bootstrap-allowlist shape, one level down: platform-admin (above) is
operator-of-the-whole-platform standing and grants nothing *within* any one
tenant (D4 — the two planes are deliberately kept separate, see
``Principal``'s docstring). Actually managing one tenant's own catalog needs
a real ``TenantMembership``, and nothing anywhere in this codebase creates
one automatically — there is no invite/onboarding flow yet (M9 territory).
This is the interim bootstrap for exactly that gap, scoped to one
operator-configured (email, tenant) pair rather than a set, since only one
tenant exists to bootstrap into today; widen to a mapping if a second
tenant ever needs its own bootstrap owner. Idempotent by an explicit check
(not a DB constraint, unlike the platform-admin grant's ``ON CONFLICT DO
NOTHING``) — low-contention, login-time only, not the kind of concurrent
double-grant CLAUDE.md's quota-checking rule is about.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from app.entities.identity import Identity
from app.entities.roles import Role
from app.entities.session import Session
from app.entities.tenant_membership import TenantMembership
from app.entities.user import User
from app.services.ports.identity_provider import IdentityProvider
from app.services.ports.token_issuer import AccessTokenClaims, TokenIssuer
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.principal_resolver import PrincipalResolver
from app.shared.clock import Clock
from app.shared.errors import AuthenticationError
from app.shared.ids import TenantId, UserId, new_session_id
from app.shared.tokens import generate_token, hash_token

REFRESH_TOKEN_TTL = timedelta(days=30)


@dataclass(frozen=True)
class LoginResult:
    user_id: UserId
    access_token: str
    refresh_token: str


class CompleteLogin:
    def __init__(
        self,
        identity_provider: IdentityProvider,
        token_issuer: TokenIssuer,
        uow_factory: UnitOfWorkFactory,
        clock: Clock,
        *,
        bootstrap_admin_emails: frozenset[str] = frozenset(),
        bootstrap_owner_email: str | None = None,
        bootstrap_owner_tenant_id: TenantId | None = None,
    ) -> None:
        self._identity_provider = identity_provider
        self._token_issuer = token_issuer
        self._uow_factory = uow_factory
        self._clock = clock
        self._bootstrap_admin_emails = frozenset(email.lower() for email in bootstrap_admin_emails)
        self._bootstrap_owner_email = (
            bootstrap_owner_email.lower() if bootstrap_owner_email else None
        )
        self._bootstrap_owner_tenant_id = bootstrap_owner_tenant_id

    async def __call__(
        self,
        *,
        code: str,
        redirect_uri: str,
        nonce: str,
        expected_state: str,
        received_state: str,
    ) -> LoginResult:
        # A plain equality check, not cryptographic - CSRF protection on the
        # redirect round-trip, deliberately kept here rather than left to
        # whoever wires the callback route to remember (see the port and
        # this module's docstrings).
        if expected_state != received_state:
            raise AuthenticationError("State parameter mismatch.")

        claims = await self._identity_provider.exchange_code(
            code=code, redirect_uri=redirect_uri, nonce=nonce
        )
        if not claims.email:
            raise AuthenticationError("Identity provider did not return an email claim.")

        now = self._clock.now()

        async with self._uow_factory(None) as uow:
            identity = await uow.identities.get_by_provider_subject(
                self._identity_provider.provider_name, claims.issuer, claims.subject
            )

            if identity is not None:
                user = await uow.users.get(identity.user_id)
                if user is None:
                    raise AuthenticationError("Identity references a user that no longer exists.")
            else:
                user = await uow.users.get_by_email(claims.email)
                if user is None:
                    user = User.register(claims.email, now=now, display_name=claims.name)
                    await uow.users.add(user)
                identity = Identity.create(
                    user.id,
                    provider=self._identity_provider.provider_name,
                    issuer=claims.issuer,
                    subject=claims.subject,
                    raw_claims=claims.raw,
                    now=now,
                )
                await uow.identities.add(identity)

            if claims.email_verified and not user.email_verified:
                user.email_verified = True
                await uow.users.update(user)

            if user.email.lower() in self._bootstrap_admin_emails:
                await uow.platform_admins.grant(user.id, granted_by=user.id, now=now)

            if (
                self._bootstrap_owner_tenant_id is not None
                and user.email.lower() == self._bootstrap_owner_email
            ):
                existing_membership = await uow.tenant_memberships.get(
                    self._bootstrap_owner_tenant_id, user.id
                )
                if existing_membership is None:
                    await uow.tenant_memberships.add(
                        TenantMembership.create(
                            self._bootstrap_owner_tenant_id, user.id, role=Role.OWNER, now=now
                        )
                    )

            refresh_token = generate_token()
            session = Session(
                id=new_session_id(),
                user_id=user.id,
                tenant_id=None,
                refresh_token_hash=hash_token(refresh_token),
                previous_token_hash=None,
                expires_at=now + REFRESH_TOKEN_TTL,
                revoked_at=None,
                created_at=now,
            )
            await uow.sessions.add(session)

            principal = await PrincipalResolver(
                uow.tenant_memberships, uow.platform_admins
            ).resolve(user.id, None)

        access_token = self._token_issuer.encode(
            AccessTokenClaims(
                subject=str(user.id),
                tenant_id=None,
                role=None,
                capabilities=[],
                is_platform_admin=principal.is_platform_admin,
            ),
            now=now,
        )
        return LoginResult(user_id=user.id, access_token=access_token, refresh_token=refresh_token)
