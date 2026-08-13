"""Who is making this request, and what they may do (D4).

Two planes, kept structurally separate rather than one flat permission set:

- ``role`` / ``capabilities`` describe standing within ``tenant_id``, if any.
- ``is_platform_admin`` is the operator plane and grants nothing here. A
  platform admin with no membership in a tenant has no tenant capabilities —
  the same "explicit grant, never inferred" discipline D4 applies to the
  admin grant itself applies again one level down: platform-admin status
  alone is not sufficient for a tenant action either. The audited,
  time-boxed exception is impersonation (not yet built), not this flag.

``capabilities`` is ``frozenset[str]``, not ``frozenset[Capability]`` — a
membership's ``extra_capabilities`` (see ``TenantMembership``) is deliberately
an escape hatch for a tenant-specific grant that was never meant to be a
named, reusable ``Capability``. Checking with a ``Capability`` enum member
still works and is the normal call shape: ``StrEnum`` members hash and
compare equal to their string value, confirmed before relying on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.entities.capabilities import Capability
from app.entities.roles import Role
from app.shared.errors import PermissionDeniedError
from app.shared.ids import TenantId, UserId


@dataclass(frozen=True)
class Principal:
    user_id: UserId
    tenant_id: TenantId | None
    role: Role | None
    capabilities: frozenset[str] = field(default_factory=frozenset)
    is_platform_admin: bool = False

    def has_capability(self, capability: Capability | str) -> bool:
        return str(capability) in self.capabilities

    def require_capability(self, capability: Capability | str) -> None:
        if not self.has_capability(capability):
            raise PermissionDeniedError(
                f"Missing capability {str(capability)!r}.",
                details={
                    "capability": str(capability),
                    "role": self.role.value if self.role else None,
                },
            )

    def require_platform_admin(self) -> None:
        if not self.is_platform_admin:
            raise PermissionDeniedError("Platform admin access required.")
