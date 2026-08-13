"""The transaction boundary.

One use case, one transaction — ``features`` opens exactly one ``UnitOfWork``
per call. The implementation is responsible for the tenant isolation guard
(D3): every statement run inside the transaction must see
``current_setting('app.current_tenant')`` set via ``SET LOCAL``, scoped to that
transaction, before any tenant-scoped query runs.

``tenant_id=None`` is for genuinely tenant-free work — platform-plane
operations, and the migrations/bootstrap paths that run as the owner role.
Everything else must pass a tenant.
"""

from __future__ import annotations

from types import TracebackType
from typing import Protocol

from app.shared.ids import TenantId


class UnitOfWork(Protocol):
    async def __aenter__(self) -> UnitOfWork:
        """Begin the transaction and apply the tenant scope."""
        ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Commit on a clean exit, roll back if the block raised."""
        ...


class UnitOfWorkFactory(Protocol):
    """What a use case actually depends on — it asks for a scoped unit of work
    rather than being handed an already-open one, so it controls exactly one
    transaction's lifetime."""

    def __call__(self, tenant_id: TenantId | None = None) -> UnitOfWork: ...
