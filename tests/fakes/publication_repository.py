from __future__ import annotations

from datetime import datetime

from app.entities.publication import Publication, PublicationStatus
from app.shared.ids import ProductVariantId, PublicationId, SocialAccountId, TenantId

_LIVE_STATUSES = (
    PublicationStatus.SCHEDULED,
    PublicationStatus.DISPATCHING,
    PublicationStatus.FAILED,
)


class InMemoryPublicationRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, PublicationId], Publication] = {}

    async def get(self, tenant_id: TenantId, publication_id: PublicationId) -> Publication | None:
        return self._rows.get((tenant_id, publication_id))

    async def get_live(
        self, tenant_id: TenantId, variant_id: ProductVariantId, channel_id: SocialAccountId
    ) -> Publication | None:
        for (tid, _), row in self._rows.items():
            if (
                tid == tenant_id
                and row.variant_id == variant_id
                and row.channel_id == channel_id
                and row.status in _LIVE_STATUSES
            ):
                return row
        return None

    async def list_due_for_release(
        self, tenant_id: TenantId, *, before: datetime, limit: int
    ) -> list[Publication]:
        matches = [
            row
            for (tid, _), row in self._rows.items()
            if tid == tenant_id
            and row.status is PublicationStatus.SCHEDULED
            and row.due_at <= before
        ]
        matches.sort(key=lambda row: row.due_at)
        return matches[:limit]

    async def add(self, publication: Publication) -> None:
        self._rows[(publication.tenant_id, publication.id)] = publication

    async def update(self, publication: Publication) -> None:
        self._rows[(publication.tenant_id, publication.id)] = publication
