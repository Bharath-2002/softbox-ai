"""Tenant membership roles and what each one grants (D4).

``ROLE_CAPABILITIES`` is the static part of capability resolution — what a
role means, decoupled from any particular request. Turning that plus a
membership's ``extra_capabilities`` into a resolved ``Principal`` for one
request is ``PrincipalResolver``'s job (``app.services``), since that needs
repository lookups this module must not depend on.

Deliberately a small, working hierarchy rather than a fully worked-out
permission model: OWNER and ADMIN currently grant the same capabilities and
are kept distinct as roles because they mean different things for billing and
deletion, neither of which exists yet. Refine when those features do, not
speculatively now.
"""

from __future__ import annotations

from enum import StrEnum

from app.entities.capabilities import Capability


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    CATALOG_MANAGER = "catalog_manager"
    APPROVER = "approver"
    VIEWER = "viewer"


_MANAGER_CAPABILITIES: frozenset[Capability] = frozenset(
    {
        Capability.CATALOG_PUBLISH,
        Capability.TEMPLATE_MANAGE,
        Capability.PRODUCT_MANAGE,
        Capability.TAXONOMY_MANAGE,
    }
)

ROLE_CAPABILITIES: dict[Role, frozenset[Capability]] = {
    Role.OWNER: _MANAGER_CAPABILITIES
    | {Capability.CATALOG_APPROVE, Capability.MEMBER_MANAGE, Capability.SETTINGS_MANAGE},
    Role.ADMIN: _MANAGER_CAPABILITIES
    | {Capability.CATALOG_APPROVE, Capability.MEMBER_MANAGE, Capability.SETTINGS_MANAGE},
    Role.CATALOG_MANAGER: _MANAGER_CAPABILITIES,
    Role.APPROVER: frozenset({Capability.CATALOG_APPROVE}),
    Role.VIEWER: frozenset(),
}
