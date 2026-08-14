"""Claims the next due `content_draft.generate_requested` job and hands back
everything `agents.copywriting` needs for the `TextGeneration` call it
makes *outside* this transaction — the composed prompt, model (stamped into
the job payload at enqueue time by `GenerateContentDraft`), and the
tenant's resolved `content.forbidden_claims` setting.

Unlike `StartGenerationItemRender`, there is no pre-existing `pending` row
to mark `running` — `entities.content_draft`'s single-member status enum is
deliberate (see its own docstring), so nothing is written here at all; the
`task_queue_jobs` row itself is the only "this is in flight" marker until
`CompleteContentDraftGeneration` creates the `content_draft` row on
success.

`content.forbidden_claims` is resolved and **type-checked** here, before
any provider call — a malformed stored value (anything that is not a list
of strings) fails the job immediately rather than silently validating the
generated copy against nothing, the same fail-closed posture
`CompleteCatalogImageQc` applies to `approval.required`. An unset value
(`None`, every tenant today) legitimately means "no forbidden claims" and
resolves to `[]` — that is not the same case as a malformed one and must
not be conflated with it.

Unlike the missing-variant case just above (a data inconsistency, where a
retry is as likely to succeed as not, so it is left `running` for the
stuck-job reaper the same way `StartGenerationItemRender` leaves its own
missing-reference-asset case), a malformed setting is **tenant
configuration** — identical on every retry, forever. Leaving that case for
the reaper would mean a job that cycles `running` -> reaped -> `running`
indefinitely, since nothing on this path ever calls `TaskQueue.fail` to
advance `attempts` toward `dead`. So this one calls `fail()` explicitly,
with the validation message, the same "an un-retryable job needs a clear
terminal, not an infinite loop" reasoning applied consistently across both
cases even though the mechanism differs.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.services.copy_prompt_composition import compose_copy_prompt
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.prompt_composition import merge_attributes
from app.services.settings_resolver import SettingsResolver
from app.shared.clock import Clock
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import ProductVariantId, TenantId

JOB_TYPE = "content_draft.generate_requested"
CLAIMED_BY = "copywriting-worker"
_FORBIDDEN_CLAIMS_KEY = "content.forbidden_claims"


@dataclass(frozen=True)
class ContentDraftGenerationContext:
    job_id: UUID
    variant_id: ProductVariantId
    channel: str
    locale: str
    prompt: str
    model: str
    forbidden_claims: list[str]


def resolve_forbidden_claims(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise ValidationError(f"{_FORBIDDEN_CLAIMS_KEY!r} must be a list of strings, got {value!r}.")


class StartContentDraftGeneration:
    def __init__(self, uow_factory: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._clock = clock

    async def __call__(self, *, tenant_id: TenantId) -> ContentDraftGenerationContext | None:
        now = self._clock.now()
        async with self._uow_factory(tenant_id) as uow:
            job = await uow.task_queue.claim(
                tenant_id, claimed_by=CLAIMED_BY, job_type=JOB_TYPE, now=now
            )
            if job is None:
                return None

            variant_id = ProductVariantId(UUID(job.payload["variant_id"]))
            channel = job.payload["channel"]
            locale = job.payload["locale"]
            model = job.payload["model"]

            variant = await uow.product_variants.get(tenant_id, variant_id)
            if variant is None:
                # Data inconsistency, not a retryable provider failure - the
                # variant this job pointed at is gone. Dead-letter the job
                # rather than retrying forever against nothing to claim.
                await uow.task_queue.fail(
                    tenant_id, job.id, error=f"product variant {variant_id} not found", now=now
                )
                return None

            product = await uow.products.get(tenant_id, variant.product_id)
            if product is None:
                raise NotFoundError("Product not found.")

            resolver = SettingsResolver(uow.settings, uow.categories)
            raw_forbidden_claims = await resolver.resolve(
                tenant_id,
                _FORBIDDEN_CLAIMS_KEY,
                category_id=product.category_id,
                product_id=product.id,
            )
            try:
                forbidden_claims = resolve_forbidden_claims(raw_forbidden_claims)
            except ValidationError as exc:
                # Tenant configuration, not a data inconsistency - identical
                # on every retry, so it must not be left for the reaper (see
                # this module's own docstring): fail the job outright.
                await uow.task_queue.fail(tenant_id, job.id, error=str(exc), now=now)
                return None

            merged_attributes = merge_attributes(product.attributes, variant.attributes)
            prompt = compose_copy_prompt(
                channel=channel, locale=locale, attributes=merged_attributes
            )

            return ContentDraftGenerationContext(
                job_id=job.id,
                variant_id=variant_id,
                channel=channel,
                locale=locale,
                prompt=prompt,
                model=model,
                forbidden_claims=forbidden_claims,
            )
