"""HTTP-level tests for ``POST /api/v1/platform/impersonate``.

Only ``get_uow_factory``/``get_clock``/``get_token_issuer`` are overridden —
``get_start_impersonation`` runs for real, proving the actual DI wiring, the
same approach ``test_auth_router.py`` uses.
"""

from __future__ import annotations

from datetime import UTC, datetime

from httpx import ASGITransport, AsyncClient

from app.api.deps.authorization import get_token_issuer
from app.bootstrap.app import create_app
from app.bootstrap.di import get_clock, get_uow_factory
from app.bootstrap.settings import Settings
from app.entities.roles import Role
from app.entities.tenant_membership import TenantMembership
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.clock import utcnow
from app.shared.ids import new_tenant_id, new_tenant_membership_id, new_user_id
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"
NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _build() -> tuple[object, FakeUnitOfWorkFactory, FakeClock, AccessTokenCodec]:
    settings = Settings(
        environment="test", log_format="console", access_token_signing_key=SIGNING_KEY
    )
    app = create_app(settings)
    uow_factory = FakeUnitOfWorkFactory()
    clock = FakeClock(NOW)
    codec = AccessTokenCodec(SIGNING_KEY)

    app.dependency_overrides[get_uow_factory] = lambda: uow_factory
    app.dependency_overrides[get_clock] = lambda: clock
    app.dependency_overrides[get_token_issuer] = lambda: codec
    return app, uow_factory, clock, codec


def _platform_admin_token(codec: AccessTokenCodec, user_id: object) -> str:
    # Encoded against real utcnow(), not the fixed FakeClock NOW below -
    # get_current_principal checks expiry against real wall-clock time
    # internally, deliberately (see test_authorization_deps.py's module
    # docstring). A token stamped 2026-01-01 would already be "expired"
    # relative to whenever this suite actually runs.
    return codec.encode(
        AccessTokenClaims(
            subject=str(user_id),
            tenant_id=None,
            role=None,
            capabilities=[],
            is_platform_admin=True,
        ),
        now=utcnow(),
    )


def _ordinary_token(codec: AccessTokenCodec, user_id: object, tenant_id: object) -> str:
    return codec.encode(
        AccessTokenClaims(
            subject=str(user_id),
            tenant_id=str(tenant_id),
            role="viewer",
            capabilities=[],
            is_platform_admin=False,
        ),
        now=utcnow(),
    )


async def _client(app: object) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_impersonate_requires_platform_admin() -> None:
    app, _uow, _clock, codec = _build()
    tenant_id = new_tenant_id()
    non_admin_token = _ordinary_token(codec, new_user_id(), tenant_id)

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/platform/impersonate",
            json={
                "target_user_id": str(new_user_id()),
                "target_tenant_id": str(tenant_id),
                "reason": "r",
            },
            headers={"Authorization": f"Bearer {non_admin_token}"},
        )

    assert response.status_code == 403


async def test_impersonate_requires_a_bearer_token() -> None:
    app, _uow, _clock, _codec = _build()

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/platform/impersonate",
            json={
                "target_user_id": str(new_user_id()),
                "target_tenant_id": str(new_tenant_id()),
                "reason": "r",
            },
        )

    assert response.status_code == 401


async def test_impersonate_succeeds_for_a_platform_admin_and_returns_a_token() -> None:
    app, uow_factory, clock, codec = _build()
    admin_id = new_user_id()
    target_id = new_user_id()
    tenant_id = new_tenant_id()
    await uow_factory.tenant_memberships.add(
        TenantMembership(
            id=new_tenant_membership_id(),
            tenant_id=tenant_id,
            user_id=target_id,
            role=Role.VIEWER,
            extra_capabilities=[],
            created_at=clock.now(),
        )
    )
    token = _platform_admin_token(codec, admin_id)

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/platform/impersonate",
            json={
                "target_user_id": str(target_id),
                "target_tenant_id": str(tenant_id),
                "reason": "Support ticket #42",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    access_token = response.json()["access_token"]
    decoded = codec.decode(access_token, now=clock.now())
    assert decoded.subject == str(target_id)
    assert decoded.impersonated_by == str(admin_id)
    assert decoded.is_platform_admin is False

    entries = await uow_factory.audit_log.list_for_subject(tenant_id, "user", target_id)
    assert entries[0].action == "impersonation.started"
    assert entries[0].after == {"reason": "Support ticket #42"}


async def test_impersonate_a_target_with_no_membership_is_404() -> None:
    app, _uow, _clock, codec = _build()
    token = _platform_admin_token(codec, new_user_id())

    async with await _client(app) as http:
        response = await http.post(
            "/api/v1/platform/impersonate",
            json={
                "target_user_id": str(new_user_id()),
                "target_tenant_id": str(new_tenant_id()),
                "reason": "r",
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404
