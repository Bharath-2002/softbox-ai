"""A hostname a storefront request's tenant is resolved from (D4,
docs/DIAGRAMS.md 5a).

``hostname`` is normalised to lowercase at creation — Host headers are
case-insensitive (RFC 3986) and the DB's ``UNIQUE (hostname)`` constraint is
not, so two differently-cased requests for the same domain must resolve to
the same stored row rather than silently missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.shared.errors import ValidationError
from app.shared.ids import TenantDomainId, TenantId, new_tenant_domain_id


@dataclass
class TenantDomain:
    id: TenantDomainId
    tenant_id: TenantId
    hostname: str
    is_primary: bool
    verified: bool
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        hostname: str,
        *,
        is_primary: bool = False,
        now: datetime,
    ) -> TenantDomain:
        normalised = hostname.strip().lower()
        if not normalised:
            raise ValidationError("Hostname must not be empty.")

        return TenantDomain(
            id=new_tenant_domain_id(),
            tenant_id=tenant_id,
            hostname=normalised,
            is_primary=is_primary,
            verified=False,
            created_at=now,
            updated_at=now,
        )
