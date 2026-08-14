from __future__ import annotations

from app.entities.publication import Publication
from app.shared.ids import PublicationId, TenantId


class InMemoryPublicationRepository:
    def __init__(self) -> None:
        self._rows: dict[tuple[TenantId, PublicationId], Publication] = {}

    async def get(self, tenant_id: TenantId, publication_id: PublicationId) -> Publication | None:
        return self._rows.get((tenant_id, publication_id))

    async def add(self, publication: Publication) -> None:
        self._rows[(publication.tenant_id, publication.id)] = publication

    async def update(self, publication: Publication) -> None:
        self._rows[(publication.tenant_id, publication.id)] = publication
