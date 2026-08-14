"""Loops every active tenant and relays each one's outbox in turn.

Opens **no transaction of its own** — the same "orchestrates between
separate single-transaction use cases" shape `agents/` uses for
LLM-driven work, minus the LLM. Doesn't live in `agents/` because that
layer is reserved for LLM-driven orchestrators (CLAUDE.md's layer table);
this is a plain multi-tenant driver. `RelayOutboxEventsForTenant` (this
package) is the actual, single-transaction unit of work; this class exists
only to discover which tenants to call it for.

One tenant's failure (a raised exception mid-relay) does not stop the
others — the alternative (one exception aborts the whole sweep) would let
a single bad tenant starve every other tenant's relay indefinitely, which
is worse than that tenant's events waiting one more cycle.
"""

from __future__ import annotations

from app.features.system.relay_outbox_events_for_tenant import RelayOutboxEventsForTenant
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.shared.ids import TenantId
from app.shared.logging import get_logger

_logger = get_logger(__name__)


class RelayOutboxEvents:
    def __init__(
        self, uow_factory: UnitOfWorkFactory, relay_for_tenant: RelayOutboxEventsForTenant
    ) -> None:
        self._uow_factory = uow_factory
        self._relay_for_tenant = relay_for_tenant

    async def __call__(self) -> dict[TenantId, int]:
        async with self._uow_factory(None) as uow:
            tenant_ids = await uow.tenants.list_active()

        relayed: dict[TenantId, int] = {}
        for tenant_id in tenant_ids:
            try:
                relayed[tenant_id] = await self._relay_for_tenant(tenant_id)
            except Exception:
                _logger.exception("outbox_relay.tenant_failed", tenant_id=str(tenant_id))
                relayed[tenant_id] = 0
        return relayed
