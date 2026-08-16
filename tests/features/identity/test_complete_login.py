"""CompleteLogin against the fake IdentityProvider and an in-memory unit of
work — no database, no network. See the module docstring on
``AuthlibIdentityProvider`` and ``test_oidc_provider_contract.py`` for why the
real Authlib path gets its own, separate, narrower test instead.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.roles import Role
from app.features.identity.complete_login import CompleteLogin
from app.infrastructure.auth.access_tokens import AccessTokenCodec
from app.services.ports.identity_provider import OidcClaims
from app.shared.errors import AuthenticationError
from app.shared.ids import new_tenant_id
from tests.fakes.clock import FakeClock
from tests.fakes.identity_provider import FakeIdentityProvider
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

REDIRECT_URI = "https://app.example.com/auth/callback"
SIGNING_KEY = "a-sufficiently-long-signing-secret-for-tests-only"


def _use_case() -> tuple[CompleteLogin, FakeIdentityProvider, FakeClock, FakeUnitOfWorkFactory]:
    provider = FakeIdentityProvider("google")
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    use_case = CompleteLogin(provider, codec, uow_factory, clock)
    return use_case, provider, clock, uow_factory


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


async def test_state_mismatch_is_rejected_before_any_provider_call() -> None:
    use_case, provider, _clock, _uow = _use_case()
    provider.register_code("code-1", _claims())

    with pytest.raises(AuthenticationError, match="State"):
        await use_case(
            code="code-1",
            redirect_uri=REDIRECT_URI,
            nonce="n",
            expected_state="expected",
            received_state="different",
        )

    # The exchange never happened - no URL was built, nothing was consumed.
    assert provider.built_urls == []


async def test_first_login_creates_a_user_and_identity() -> None:
    use_case, provider, _clock, uow_factory = _use_case()
    provider.register_code("code-1", _claims())

    result = await use_case(
        code="code-1",
        redirect_uri=REDIRECT_URI,
        nonce="n",
        expected_state="s",
        received_state="s",
    )

    user = await uow_factory.users.get(result.user_id)
    assert user is not None
    assert user.email == "person@example.com"

    identity = await uow_factory.identities.get_by_provider_subject(
        "google", "https://accounts.google.com", "provider-subject-1"
    )
    assert identity is not None
    assert identity.user_id == result.user_id


async def test_returning_identity_reuses_the_same_user_and_creates_no_second_one() -> None:
    use_case, provider, _clock, uow_factory = _use_case()
    provider.register_code("code-1", _claims())
    first = await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    provider.register_code("code-2", _claims())  # same subject/issuer
    second = await use_case(
        code="code-2", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    assert second.user_id == first.user_id
    assert len(uow_factory.users._rows) == 1


async def test_a_second_provider_for_an_existing_email_links_to_the_same_user() -> None:
    """The email-fallback path: a different (provider, issuer, subject)
    reaching an email that already has an account links a new Identity to
    the existing User rather than creating a second one."""
    use_case, provider, _clock, uow_factory = _use_case()
    provider.register_code("code-1", _claims(subject="google-subject"))
    first = await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    provider.register_code(
        "code-2",
        _claims(subject="microsoft-subject", issuer="https://login.microsoftonline.com/tenant"),
    )
    second = await use_case(
        code="code-2", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    assert second.user_id == first.user_id
    assert len(uow_factory.users._rows) == 1


async def test_missing_email_claim_is_rejected() -> None:
    use_case, provider, _clock, _uow = _use_case()
    provider.register_code("code-1", _claims(email=None))

    with pytest.raises(AuthenticationError, match="email"):
        await use_case(
            code="code-1",
            redirect_uri=REDIRECT_URI,
            nonce="n",
            expected_state="s",
            received_state="s",
        )


async def test_invalid_authorization_code_is_rejected() -> None:
    use_case, _provider, _clock, _uow = _use_case()

    with pytest.raises(AuthenticationError):
        await use_case(
            code="never-registered",
            redirect_uri=REDIRECT_URI,
            nonce="n",
            expected_state="s",
            received_state="s",
        )


async def test_email_verified_is_synced_from_the_provider() -> None:
    use_case, provider, _clock, uow_factory = _use_case()
    provider.register_code("code-1", _claims(email_verified=False))
    result = await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )
    user = await uow_factory.users.get(result.user_id)
    assert user is not None
    assert user.email_verified is False

    provider.register_code("code-2", _claims(email_verified=True))
    await use_case(
        code="code-2", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )
    user = await uow_factory.users.get(result.user_id)
    assert user is not None
    assert user.email_verified is True


async def test_the_issued_access_token_carries_no_tenant_and_no_capabilities() -> None:
    """Login never binds a tenant - see the module docstring."""
    use_case, provider, clock, _uow = _use_case()
    provider.register_code("code-1", _claims())
    result = await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    codec = AccessTokenCodec(SIGNING_KEY)
    decoded = codec.decode(result.access_token, now=clock.now())

    assert decoded.tenant_id is None
    assert decoded.role is None
    assert decoded.capabilities == []


async def test_an_allowlisted_email_is_granted_platform_admin_on_first_login() -> None:
    """No second login required, unlike the manually-granted case below -
    the allowlist grant must apply within the same transaction as the very
    first login that creates the user."""
    provider = FakeIdentityProvider("google")
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    use_case = CompleteLogin(
        provider,
        codec,
        uow_factory,
        clock,
        bootstrap_admin_emails=frozenset({"person@example.com"}),
    )
    provider.register_code("code-1", _claims(email="person@example.com"))

    result = await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    assert await uow_factory.platform_admins.is_admin(result.user_id) is True
    decoded = codec.decode(result.access_token, now=clock.now())
    assert decoded.is_platform_admin is True


async def test_allowlist_comparison_is_case_insensitive() -> None:
    provider = FakeIdentityProvider("google")
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    use_case = CompleteLogin(
        provider,
        codec,
        uow_factory,
        clock,
        bootstrap_admin_emails=frozenset({"person@example.com"}),
    )
    provider.register_code("code-1", _claims(email="Person@Example.com"))

    result = await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    assert await uow_factory.platform_admins.is_admin(result.user_id) is True


async def test_a_non_allowlisted_email_is_not_granted_platform_admin() -> None:
    provider = FakeIdentityProvider("google")
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    use_case = CompleteLogin(
        provider,
        codec,
        uow_factory,
        clock,
        bootstrap_admin_emails=frozenset({"someone-else@example.com"}),
    )
    provider.register_code("code-1", _claims(email="person@example.com"))

    result = await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    assert await uow_factory.platform_admins.is_admin(result.user_id) is False


async def test_logging_in_twice_with_an_allowlisted_email_does_not_error() -> None:
    """The grant is ON CONFLICT DO NOTHING at the repository level - a
    second login must not raise on the already-granted case."""
    provider = FakeIdentityProvider("google")
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    use_case = CompleteLogin(
        provider,
        codec,
        uow_factory,
        clock,
        bootstrap_admin_emails=frozenset({"person@example.com"}),
    )
    provider.register_code("code-1", _claims(email="person@example.com"))
    provider.register_code("code-2", _claims(email="person@example.com"))

    await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )
    result = await use_case(
        code="code-2", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    assert await uow_factory.platform_admins.is_admin(result.user_id) is True


async def test_a_platform_admin_gets_the_flag_on_their_token() -> None:
    use_case, provider, clock, uow_factory = _use_case()
    provider.register_code("code-1", _claims())
    result = await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )
    await uow_factory.platform_admins.grant(
        result.user_id, granted_by=result.user_id, now=clock.now()
    )

    provider.register_code("code-2", _claims())  # a second login, now as an admin
    second = await use_case(
        code="code-2", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    codec = AccessTokenCodec(SIGNING_KEY)
    decoded = codec.decode(second.access_token, now=clock.now())
    assert decoded.is_platform_admin is True


async def test_an_allowlisted_owner_email_is_granted_ownership_on_first_login() -> None:
    provider = FakeIdentityProvider("google")
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    tenant_id = new_tenant_id()
    use_case = CompleteLogin(
        provider,
        codec,
        uow_factory,
        clock,
        bootstrap_owner_email="owner@example.com",
        bootstrap_owner_tenant_id=tenant_id,
    )
    provider.register_code("code-1", _claims(email="owner@example.com"))

    result = await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    membership = await uow_factory.tenant_memberships.get(tenant_id, result.user_id)
    assert membership is not None
    assert membership.role is Role.OWNER


async def test_owner_allowlist_comparison_is_case_insensitive() -> None:
    provider = FakeIdentityProvider("google")
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    tenant_id = new_tenant_id()
    use_case = CompleteLogin(
        provider,
        codec,
        uow_factory,
        clock,
        bootstrap_owner_email="owner@example.com",
        bootstrap_owner_tenant_id=tenant_id,
    )
    provider.register_code("code-1", _claims(email="Owner@Example.com"))

    result = await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    assert await uow_factory.tenant_memberships.get(tenant_id, result.user_id) is not None


async def test_a_non_allowlisted_email_gets_no_bootstrap_membership() -> None:
    provider = FakeIdentityProvider("google")
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    tenant_id = new_tenant_id()
    use_case = CompleteLogin(
        provider,
        codec,
        uow_factory,
        clock,
        bootstrap_owner_email="owner@example.com",
        bootstrap_owner_tenant_id=tenant_id,
    )
    provider.register_code("code-1", _claims(email="person@example.com"))

    result = await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    assert await uow_factory.tenant_memberships.get(tenant_id, result.user_id) is None


async def test_no_bootstrap_tenant_configured_grants_no_membership() -> None:
    """Both settings must be present - an operator-configured email with no
    configured tenant must not silently grant membership somewhere."""
    use_case, provider, _clock, uow_factory = _use_case()
    provider.register_code("code-1", _claims(email="person@example.com"))

    result = await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    assert await uow_factory.tenant_memberships.list_for_user(result.user_id) == []


async def test_logging_in_twice_with_an_allowlisted_owner_email_does_not_duplicate() -> None:
    provider = FakeIdentityProvider("google")
    clock = FakeClock(datetime(2026, 1, 1, tzinfo=UTC))
    uow_factory = FakeUnitOfWorkFactory()
    codec = AccessTokenCodec(SIGNING_KEY)
    tenant_id = new_tenant_id()
    use_case = CompleteLogin(
        provider,
        codec,
        uow_factory,
        clock,
        bootstrap_owner_email="owner@example.com",
        bootstrap_owner_tenant_id=tenant_id,
    )
    provider.register_code("code-1", _claims(email="owner@example.com"))
    provider.register_code("code-2", _claims(email="owner@example.com"))

    await use_case(
        code="code-1", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )
    result = await use_case(
        code="code-2", redirect_uri=REDIRECT_URI, nonce="n", expected_state="s", received_state="s"
    )

    memberships = await uow_factory.tenant_memberships.list_for_user(result.user_id)
    assert len(memberships) == 1
    assert memberships[0].role is Role.OWNER
