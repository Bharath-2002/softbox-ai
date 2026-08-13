from __future__ import annotations

import pytest

from app.entities.capabilities import Capability
from app.entities.roles import ROLE_CAPABILITIES, Role


def test_every_role_has_an_entry() -> None:
    assert set(ROLE_CAPABILITIES) == set(Role)


def test_viewer_has_no_gated_capabilities() -> None:
    assert ROLE_CAPABILITIES[Role.VIEWER] == frozenset()


def test_approver_can_only_approve() -> None:
    assert ROLE_CAPABILITIES[Role.APPROVER] == frozenset({Capability.CATALOG_APPROVE})


@pytest.mark.parametrize(
    "capability",
    [Capability.CATALOG_PUBLISH, Capability.TEMPLATE_MANAGE, Capability.PRODUCT_MANAGE],
)
def test_catalog_manager_has_the_working_capabilities(capability: Capability) -> None:
    assert capability in ROLE_CAPABILITIES[Role.CATALOG_MANAGER]


def test_catalog_manager_cannot_approve_or_manage_members() -> None:
    manager = ROLE_CAPABILITIES[Role.CATALOG_MANAGER]
    assert Capability.CATALOG_APPROVE not in manager
    assert Capability.MEMBER_MANAGE not in manager


@pytest.mark.parametrize("role", [Role.OWNER, Role.ADMIN])
def test_owner_and_admin_hold_every_capability(role: Role) -> None:
    assert ROLE_CAPABILITIES[role] == frozenset(Capability)
