"""Orchestrates D20's QC step: claims one due `catalog_image.qc_requested`
job, fetches the generated image and its reference photos and calls the
`QualityControl` provider *between* two independent transactions, then
records the verdict or the job failure - the same shape
`agents.generation_render` (and, before it, `agents.template_analysis`)
established: the agent owns the control flow and the one call that must
not happen inside a transaction, not a transaction itself.
"""

from __future__ import annotations

from app.features.generation.complete_catalog_image_qc import CompleteCatalogImageQc
from app.features.generation.fail_catalog_image_qc import FailCatalogImageQc
from app.features.generation.start_catalog_image_qc import StartCatalogImageQc
from app.services.ports.object_storage import ObjectStorage
from app.services.ports.quality_control import QualityControl
from app.shared.ids import TenantId


class CatalogImageQcAgent:
    def __init__(
        self,
        start: StartCatalogImageQc,
        complete: CompleteCatalogImageQc,
        fail: FailCatalogImageQc,
        object_storage: ObjectStorage,
        quality_control: QualityControl,
    ) -> None:
        self._start = start
        self._complete = complete
        self._fail = fail
        self._object_storage = object_storage
        self._quality_control = quality_control

    async def run(self, *, tenant_id: TenantId) -> bool:
        """Returns `False` when nothing was claimable, `True` once a
        verdict (or job failure) was recorded - `CompleteCatalogImageQc`
        returns `None`, so a plain boolean is what tells a caller whether
        this call actually did something."""
        ctx = await self._start(tenant_id=tenant_id)
        if ctx is None:
            return False

        try:
            image_bytes = await self._object_storage.read(ctx.image_storage_key)
            reference_images = [
                await self._object_storage.read(key) for key in ctx.reference_storage_keys
            ]
            verdict = await self._quality_control.evaluate(
                image_bytes,
                reference_images=reference_images,
                slot_spec=ctx.slot_spec,
                declared_colour=ctx.declared_colour,
            )
        except Exception as exc:  # any provider/storage failure is retryable, not fatal
            await self._fail(tenant_id=tenant_id, job_id=ctx.job_id, error=str(exc))
            return True

        await self._complete(
            tenant_id=tenant_id,
            catalog_image_id=ctx.catalog_image_id,
            job_id=ctx.job_id,
            verdict=verdict,
        )
        return True
