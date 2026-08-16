"""HTTP-level tests for ``/api/v1/auth/*`` (google login/callback/refresh/
logout).

Only the four low-level port providers (``get_uow_factory``, ``get_clock``,
``get_google_identity_provider``, ``get_token_issuer``) are overridden via
``app.dependency_overrides`` — ``get_complete_login``/``get_refresh_session``/
``get_logout`` run for real, so this proves the *actual* wiring in
``bootstrap/di.py`` (including ``admin_emails`` threading), not a hand-built
stand-in use case. No real network call to Google happens anywhere in this
file: the narrower "does the real Authlib code work" question is
``test_oidc_provider_contract.py``'s job.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import get_token_issuer
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_google_identity_provider, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.roles import Role
from app.entities.session import Session
from app.entities.tenant_membership import TenantMembership
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.identity_provider import OidcClaims
from app.shared.ids import TenantId, UserId, new_session_id, new_tenant_id, new_user_id
from app.shared.tokens import generate_token, hash_token
from tests.fakes.clock import FakeClock
from tests.fakes.identity_provider import FakeIdentityProvider
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"
REDIRECT_URI = "https://app.example.com/auth/callback"


def _build(
    *,
    admin_emails: tuple[str, ...] = (),
    bootstrap_owner_email: str | None = None,
    bootstrap_owner_tenant_id: TenantId | None = None,
):
    settings = Settings(
        environment="test",
        log_format="console",
        access_token_signing_key=SIGNING_KEY,
        admin_emails=admin_emails,
        bootstrap_owner_email=bootstrap_owner_email,
        bootstrap_owner_tenant_id=bootstrap_owner_tenant_id,
    )
    app = create_app(settings)
    uow_factory = FakeUnitOfWorkFactory()
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    provider = FakeIdentityProvider("google")
    codec = AccessTokenCodec(SIGNING_KEY)

    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_google_identity_provider] = lambda: provider
    app.dependency_overrides[get_token_issuer] = lambda: codec
    return app, uow_factory, clock, provider, codec


def _claims(**overrides: object) -> OidcClaims:
    defaults: dict[str, object] = {
        "subject": "provider-subject-1",
        "issuer": "https://accounts.google.com",
        "email": "person@example.com",
        "email_verified": True,
        "name": "Person Example",
        "raw": {},
    }
    defaults.update(overrides)
    return OidcClaims(**defaults)  # type: ignore[arg-type]


async def _client(app: object) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_google_login_returns_an_authorization_url_state_and_nonce() -> None:
    app, _uow, _clock, _provider, _codec = _build()

    async with await _client(app) as http:
        response = await http.get(
            "/api/v1/auth/google/login", params={"redirect_uri": REDIRECT_URI}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["authorization_url"]
    assert body["state"]
    assert body["nonce"]


async def test_full_login_round_trip_returns_tokens() -> None:
    app, _uow, _clock, provider, codec = _build()
    provider.register_code("code-1", _claims())

    async with await _client(app) as http:
        login_response = await http.get(
            "/api/v1/auth/google/login", params={"redirect_uri": REDIRECT_URI}
        )
        state = login_response.json()["state"]
        nonce = login_response.json()["nonce"]

        callback_response = await http.post(
            "/api/v1/auth/google/callback",
            json={
                "code": "code-1",
                "redirect_uri": REDIRECT_URI,
                "state": state,
                "expected_state": state,
                "nonce": nonce,
            },
        )

    assert callback_response.status_code == 200
    body = callback_response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    decoded = codec.decode(body["access_token"], now=datetime(2026, 1, 1, tzinfo=UTC))
    assert decoded.subject


async def test_callback_with_a_state_mismatch_is_rejected() -> None:
    app, _uow, _clock, provider, _codec = _build()
    provider.register_code("code-1", _claims())

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/auth/google/callback",
            json={
                "code": "code-1",
                "redirect_uri": REDIRECT_URI,
                "state": "attacker-supplied",
                "expected_state": "the-real-one",
                "nonce": "n",
            },
        )

    assert response.status_code == 401


async def test_callback_grants_platform_admin_to_an_allowlisted_email() -> None:
    app, _uow, _clock, provider, codec = _build(admin_emails=("person@example.com",))
    provider.register_code("code-1", _claims(email="person@example.com"))

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/auth/google/callback",
            json={
                "code": "code-1",
                "redirect_uri": REDIRECT_URI,
                "state": "s",
                "expected_state": "s",
                "nonce": "n",
            },
        )

    access_token = response.json()["access_token"]
    decoded = codec.decode(access_token, now=datetime(2026, 1, 1, tzinfo=UTC))
    assert decoded.is_platform_admin is True


async def test_refresh_rotates_the_token() -> None:
    app, uow_factory, clock, _provider, _codec = _build()

    original_token = generate_token()
    session = Session(
        id=new_session_id(),
        user_id=new_user_id(),
        tenant_id=None,
        refresh_token_hash=hash_token(original_token),
        previous_token_hash=None,
        expires_at=clock.now().replace(year=2027),
        revoked_at=None,
        created_at=clock.now(),
    )
    await uow_factory.sessions.add(session)

    async with await _client(app) as http:
        response = await http.post("/api/v1/auth/refresh", json={"refresh_token": original_token})

    assert response.status_code == 200
    body = response.json()
    assert body["refresh_token"] != original_token


async def test_logout_is_idempotent_on_an_unknown_token() -> None:
    app, _uow, _clock, _provider, _codec = _build()

    async with await _client(app) as http:
        response = await http.post("/api/v1/auth/logout", json={"refresh_token": "never-issued"})

    assert response.status_code == 204


async def test_callback_grants_bootstrap_owner_membership_to_an_allowlisted_email() -> None:
    tenant_id = new_tenant_id()
    app, uow_factory, _clock, provider, codec = _build(
        bootstrap_owner_email="owner@example.com", bootstrap_owner_tenant_id=tenant_id
    )
    provider.register_code("code-1", _claims(email="owner@example.com"))

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/auth/google/callback",
            json={
                "code": "code-1",
                "redirect_uri": REDIRECT_URI,
                "state": "s",
                "expected_state": "s",
                "nonce": "n",
            },
        )

    access_token = response.json()["access_token"]
    subject = codec.decode(access_token, now=datetime(2026, 1, 1, tzinfo=UTC)).subject
    user_id = UserId(uuid.UUID(subject))
    membership = await uow_factory.tenant_memberships.get(tenant_id, user_id)
    assert membership is not None
    assert membership.role is Role.OWNER


async def test_select_tenant_over_http_returns_a_tenant_scoped_token() -> None:
    app, uow_factory, clock, _provider, codec = _build()
    token = generate_token()
    user_id = new_user_id()
    session = Session(
        id=new_session_id(),
        user_id=user_id,
        tenant_id=None,
        refresh_token_hash=hash_token(token),
        previous_token_hash=None,
        expires_at=clock.now().replace(year=2027),
        revoked_at=None,
        created_at=clock.now(),
    )
    await uow_factory.sessions.add(session)
    tenant_id = new_tenant_id()
    await uow_factory.tenant_memberships.add(
        TenantMembership.create(tenant_id, user_id, role=Role.OWNER, now=clock.now())
    )

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/auth/select-tenant",
            json={"refresh_token": token, "tenant_id": str(tenant_id)},
        )

    assert response.status_code == 200
    body = response.json()
    decoded = codec.decode(body["access_token"], now=clock.now())
    assert decoded.tenant_id == str(tenant_id)
    assert decoded.role == "owner"


async def test_select_tenant_without_membership_is_forbidden() -> None:
    app, uow_factory, clock, _provider, _codec = _build()
    token = generate_token()
    session = Session(
        id=new_session_id(),
        user_id=new_user_id(),
        tenant_id=None,
        refresh_token_hash=hash_token(token),
        previous_token_hash=None,
        expires_at=clock.now().replace(year=2027),
        revoked_at=None,
        created_at=clock.now(),
    )
    await uow_factory.sessions.add(session)

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/auth/select-tenant",
            json={"refresh_token": token, "tenant_id": str(new_tenant_id())},
        )

    assert response.status_code == 403
