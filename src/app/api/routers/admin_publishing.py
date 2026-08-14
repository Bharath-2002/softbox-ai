"""D21's publish-trigger endpoints, the same "real capability, no automatic
trigger" shape ``admin_content.py``/``admin_generation.py`` already use.

``POST /variants/{variant_id}/publications`` enqueues a publish attempt for
one ``(variant, channel)`` — commits the row and its idempotency key,
writes the outbox event, returns ``202``. Nothing has been posted to any
provider by the time the response is sent; see
``features.publishing.create_publication``'s docstring for why that split
is exactly what makes the Gate's idempotency property provable.

``POST /publications/publish-next`` is the worker step: claims whatever
publish job is oldest-due for the tenant and calls ``ChannelPublisher``
between two transactions. Gated on ``Capability.PRODUCT_MANAGE``, matching
every other worker-step trigger route in this codebase — this is
pipeline execution, not an approval action.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel

from app.api.deps.authorization import PrincipalDep, require_capability
from app.bootstrap.di import CreatePublicationDep, PublishChannelAgentDep
from app.entities.capabilities import Capability
from app.entities.publication import Publication
from app.shared.ids import AssetId, ContentDraftId, ProductVariantId, PublicationId, SocialAccountId

router = APIRouter()
_manage = [Depends(require_capability(Capability.PRODUCT_MANAGE))]


class CreatePublicationRequest(BaseModel):
    channel_id: SocialAccountId
    content_draft_id: ContentDraftId | None = None
    caption: str
    media_asset_ids: list[AssetId]
    link: str | None = None


class PublicationResponse(BaseModel):
    id: PublicationId
    variant_id: ProductVariantId
    channel_id: SocialAccountId
    status: str
    external_post_id: str | None
    permalink: str | None
    attempts: int
    last_error: str | None
    created_at: datetime

    @staticmethod
    def from_entity(p: Publication) -> PublicationResponse:
        return PublicationResponse(
            id=p.id,
            variant_id=p.variant_id,
            channel_id=p.channel_id,
            status=p.status.value,
            external_post_id=p.external_post_id,
            permalink=p.permalink,
            attempts=p.attempts,
            last_error=p.last_error,
            created_at=p.created_at,
        )


@router.post(
    "/variants/{variant_id}/publications",
    response_model=PublicationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=_manage,
)
async def create_publication(
    variant_id: ProductVariantId,
    body: CreatePublicationRequest,
    principal: PrincipalDep,
    use_case: CreatePublicationDep,
) -> PublicationResponse:
    assert principal.tenant_id is not None
    publication = await use_case(
        tenant_id=principal.tenant_id,
        variant_id=variant_id,
        channel_id=body.channel_id,
        content_draft_id=body.content_draft_id,
        caption=body.caption,
        media_asset_ids=body.media_asset_ids,
        link=body.link,
    )
    return PublicationResponse.from_entity(publication)


@router.post(
    "/publications/publish-next",
    response_model=PublicationResponse | None,
    dependencies=_manage,
)
async def publish_next(
    principal: PrincipalDep, agent: PublishChannelAgentDep
) -> PublicationResponse | None:
    assert principal.tenant_id is not None
    publication = await agent.run(tenant_id=principal.tenant_id)
    return PublicationResponse.from_entity(publication) if publication is not None else None
