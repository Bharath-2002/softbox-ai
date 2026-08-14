"""Orchestrates §6.1's `validating` step: reads the uploaded bytes and runs
Pillow analysis between two independent transactions, owning neither itself
(the same shape `TemplateAnalysisAgent` established — see its module
docstring for why an agent must never open its own `UnitOfWork`).

No separate "fail" use case, unlike `TemplateAnalysisAgent`'s three-way
split. A vision-provider failure there is worth an automatic, bounded retry
loop (`analysis_failed -> uploaded`, a real state built for it) because the
call is expensive and external. Reading local/S3 bytes and running local
Pillow analysis is neither: if it fails for any reason (a storage read
error, a corrupt file `image_inspection` should have already caught but
didn't), the honest outcome is the same as any other validation failure — a
human retakes the photo — so it routes through the ordinary `rejected` path
with a generic, actionable reason rather than a bespoke retryable state.
"""

from __future__ import annotations

from app.entities.product_input_image import ProductInputImage
from app.features.products.complete_input_image_validation import CompleteInputImageValidation
from app.features.products.start_input_image_validation import StartInputImageValidation
from app.services.input_image_validation import validate_input_image
from app.services.ports.object_storage import ObjectStorage
from app.shared.ids import ProductInputImageId, TenantId


class InputImageValidationAgent:
    def __init__(
        self,
        start: StartInputImageValidation,
        complete: CompleteInputImageValidation,
        object_storage: ObjectStorage,
    ) -> None:
        self._start = start
        self._complete = complete
        self._object_storage = object_storage

    async def run(self, *, tenant_id: TenantId, image_id: ProductInputImageId) -> ProductInputImage:
        ctx = await self._start(tenant_id=tenant_id, image_id=image_id)

        verdict_passed: bool
        verdict_reason: str | None
        try:
            data = await self._object_storage.read(ctx.storage_key)
            verdict = validate_input_image(data, width=ctx.width, height=ctx.height)
        except Exception:
            verdict_passed = False
            verdict_reason = "Could not read the uploaded photo — try uploading it again."
        else:
            verdict_passed, verdict_reason = verdict.passed, verdict.reason

        return await self._complete(
            tenant_id=tenant_id, image_id=ctx.image_id, passed=verdict_passed, reason=verdict_reason
        )
