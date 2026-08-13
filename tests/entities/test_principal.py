from __future__ import annotations

import pytest

from app.entities.capabilities import Capability
from app.entities.principal import Principal
from app.entities.roles import Role
from app.shared.errors import PermissionDeniedError
from app.shared.ids import new_tenant_id, new_user_id


def _principal(**overrides: object) -> Principal:
    defaults: dict[str, object] = {
        "user_id": new_user_id(),
        "tenant_id": new_tenant_id(),
        "role": Role.VIEWER,
        "capabilities": frozenset(),
        "is_platform_admin": False,
    }
    defaults.update(overrides)
    return Principal(**defaults)  # type: ignore[arg-type]


def test_has_capability_true_when_present() -> None:
    principal = _principal(capabilities=frozenset({Capability.CATALOG_PUBLISH}))
    assert principal.has_capability(Capability.CATALOG_PUBLISH) is True


def test_has_capability_false_when_absent() -> None:
    principal = _principal(capabilities=frozenset())
    assert principal.has_capability(Capability.CATALOG_PUBLISH) is False


def test_require_capability_raises_with_the_capability_named() -> None:
    principal = _principal(capabilities=frozenset())
    with pytest.raises(PermissionDeniedError) as exc_info:
        principal.require_capability(Capability.CATALOG_PUBLISH)
    assert exc_info.value.details["capability"] == "catalog.publish"


def test_require_capability_passes_silently_when_present() -> None:
    principal = _principal(capabilities=frozenset({Capability.CATALOG_PUBLISH}))
    principal.require_capability(Capability.CATALOG_PUBLISH)  # must not raise


def test_arbitrary_extra_capability_string_is_honoured() -> None:
    """extra_capabilities is an escape hatch for values outside the closed
    Capability enum — a plain string must still be checkable."""
    principal = _principal(capabilities=frozenset({"tenant-specific-one-off"}))
    assert principal.has_capability("tenant-specific-one-off") is True
    assert principal.has_capability(Capability.CATALOG_PUBLISH) is False


def test_platform_admin_flag_grants_nothing_tenant_side() -> None:
    """D4, generalised one level down: platform-admin status alone is not
    sufficient for a tenant capability - only actual membership is."""
    principal = _principal(capabilities=frozenset(), is_platform_admin=True)
    assert principal.has_capability(Capability.CATALOG_PUBLISH) is False


def test_require_platform_admin_raises_for_a_tenant_user() -> None:
    principal = _principal(is_platform_admin=False)
    with pytest.raises(PermissionDeniedError):
        principal.require_platform_admin()


def test_require_platform_admin_passes_for_an_actual_admin() -> None:
    principal = _principal(is_platform_admin=True)
    principal.require_platform_admin()  # must not raise
