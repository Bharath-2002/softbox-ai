"""Generation-pipeline endpoints (D18, D19) under ``/admin`` — the M5 render
step. Unlike ``admin_products.py``'s generation routes (which act on one
named ``product``/``generation_request``), ``POST .../render-next`` takes
no resource id: ``GenerationRenderAgent`` claims whatever
``generation_item.render_requested`` job is oldest-due for the tenant, the
same "the queue executes one step" shape ``TaskQueue.claim`` names (D19),
so there is no single resource this endpoint could be nested under.

Runs synchronously, inline in the request — the same known-interim shape
``POST .../templates/{id}/analyse`` already uses: there is no scheduled
poller yet (M5's reconciler, still ahead), so an admin (or, once one
exists, the poller itself) calls this explicitly. Same "real capability, no
automatic trigger" posture every other M5 admin route follows.

Returns ``null`` when nothing was claimable — the caller (a human clicking
"render next," or eventually a poll loop) can tell "nothing due right now"
apart from "one job actually ran" without a separate boolean field.

``POST .../qc-next`` is the same shape for D20's QC step:
``CatalogImageQcAgent`` claims whatever ``catalog_image.qc_requested`` job
is oldest-due. It returns a bare boolean rather than a response body,
because unlike a render attempt a QC verdict does not hand back a single
new domain object worth serialising — the caller who wants to see the
result reads the catalog image itself.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.deps.authorization import PrincipalDep, require_capability
from app.bootstrap.di import CatalogImageQcAgentDep, GenerationRenderAgentDep
from app.entities.capabilities import Capability
from app.entities.generation_item import GenerationItem
from app.shared.ids import (
    AssetId,
    CatalogImageSlotId,
    GenerationItemId,
    GenerationRequestId,
)

router = APIRouter()
_manage = [Depends(require_capability(Capability.PRODUCT_MANAGE))]


class GenerationItemResponse(BaseModel):
    id: GenerationItemId
    request_id: GenerationRequestId
    catalog_image_slot_id: CatalogImageSlotId
    attempt_no: int
    status: str
    output_asset_id: AssetId | None
    cost_micros: int | None
    latency_ms: int | None
    error_code: str | None

    @staticmethod
    def from_entity(i: GenerationItem) -> GenerationItemResponse:
        return GenerationItemResponse(
            id=i.id,
            request_id=i.request_id,
            catalog_image_slot_id=i.catalog_image_slot_id,
            attempt_no=i.attempt_no,
            status=i.status.value,
            output_asset_id=i.output_asset_id,
            cost_micros=i.cost_micros,
            latency_ms=i.latency_ms,
            error_code=i.error_code,
        )


@router.post(
    "/generation/render-next", response_model=GenerationItemResponse | None, dependencies=_manage
)
async def render_next_generation_item(
    principal: PrincipalDep, agent: GenerationRenderAgentDep
) -> GenerationItemResponse | None:
    assert principal.tenant_id is not None
    item = await agent.run(tenant_id=principal.tenant_id)
    return GenerationItemResponse.from_entity(item) if item is not None else None


class QcNextResponse(BaseModel):
    ran: bool


@router.post("/generation/qc-next", response_model=QcNextResponse, dependencies=_manage)
async def qc_next_catalog_image(
    principal: PrincipalDep, agent: CatalogImageQcAgentDep
) -> QcNextResponse:
    assert principal.tenant_id is not None
    ran = await agent.run(tenant_id=principal.tenant_id)
    return QcNextResponse(ran=ran)
