"""Registers a hostname a tenant's storefront will resolve from (D4, M8).

Uniqueness (`hostname` is global, not per-tenant) is the migration's
`UNIQUE (hostname)` constraint, not a check-then-act lookup here — a
duplicate is a 409 (`api/errors.py` maps the resulting `IntegrityError` to
`ConflictError`), the same reasoning `CreateCategory` already documents for
slug uniqueness.
"""

from __future__ import annotations

from app.entities.tenant_domain import TenantDomain
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.clock import Clock
from app.shared.ids import TenantId, UserId


class RegisterTenantDomain:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(
        self, *, tenant_id: TenantId, hostname: str, actor_user_id: UserId
    ) -> TenantDomain:
        now = self._clock.now()

        async with self._uow_factory(tenant_id) as uow:
            domain = TenantDomain.create(tenant_id, hostname, now=now)
            await uow.tenant_domains.add(domain)

            await uow.audit_log.record(
                tenant_id,
                actor_user_id=actor_user_id,
                action="tenant_domain.registered",
                subject_type="tenant_domain",
                subject_id=domain.id,
                before=None,
                after={"hostname": domain.hostname},
                now=now,
            )

            return domain
