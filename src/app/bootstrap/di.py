"""DI provider functions (CLAUDE.md §4): return **port types**, not concrete
classes, so a route depends on an interface and a test can override with a
fake via ``app.dependency_overrides``.

Everything here reads from ``app.state`` (built once in
``bootstrap.app.create_app``), the same pattern ``api/deps/*`` uses for
infrastructure ports — the difference is these construct **use cases**
(``features`` layer), which need both ports and config (like
``admin_emails``), so they belong in ``bootstrap`` (the only layer allowed
to see both ``features`` and ``infrastructure``) rather than ``api``.

This is the first module in this package — no route needed a use case
before ``/auth/*``, which chunk 4 explicitly deferred until routers existed
at all.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.agents.catalog_image_qc import CatalogImageQcAgent
from app.agents.copywriting import CopywritingAgent
from app.agents.generation_render import GenerationRenderAgent
from app.agents.input_image_validation import InputImageValidationAgent
from app.agents.publish_channel import PublishChannelAgent
from app.agents.template_analysis import TemplateAnalysisAgent
from app.api.deps.authorization import get_token_issuer
from app.api.deps.channel_publisher import get_channel_publisher
from app.api.deps.content_moderation import get_content_moderation_scanner
from app.api.deps.image_generation import get_image_generation
from app.api.deps.object_storage import get_object_storage
from app.api.deps.quality_control import get_quality_control
from app.api.deps.rate_limit import get_rate_limiter
from app.api.deps.text_generation import get_text_generation
from app.api.deps.vision_analysis import get_vision_analysis
from app.features.assets.request_download import RequestDownload
from app.features.assets.request_upload import RequestUpload
from app.features.assets.verify_and_register_upload import VerifyAndRegisterUpload
from app.features.content.approve_content_draft import ApproveContentDraft
from app.features.content.complete_content_draft_generation import (
    CompleteContentDraftGeneration,
)
from app.features.content.edit_content_draft import EditContentDraft
from app.features.content.fail_content_draft_generation import FailContentDraftGeneration
from app.features.content.generate_content_draft import GenerateContentDraft
from app.features.content.list_content_drafts_for_variant import ListContentDraftsForVariant
from app.features.content.reject_content_draft import RejectContentDraft
from app.features.content.start_content_draft_generation import StartContentDraftGeneration
from app.features.generation.approve_catalog_image import ApproveCatalogImage
from app.features.generation.bulk_approve_catalog_images_for_product import (
    BulkApproveCatalogImagesForProduct,
)
from app.features.generation.complete_catalog_image_qc import CompleteCatalogImageQc
from app.features.generation.complete_generation_item_render import CompleteGenerationItemRender
from app.features.generation.fail_catalog_image_qc import FailCatalogImageQc
from app.features.generation.fail_generation_item_render import FailGenerationItemRender
from app.features.generation.list_catalog_images_for_review import ListCatalogImagesForReview
from app.features.generation.reconcile_generation_requests_for_tenant import (
    ReconcileGenerationRequestsForTenant,
)
from app.features.generation.reject_catalog_image import RejectCatalogImage
from app.features.generation.start_catalog_image_qc import StartCatalogImageQc
from app.features.generation.start_generation_item_render import StartGenerationItemRender
from app.features.identity.complete_login import CompleteLogin
from app.features.identity.logout import Logout
from app.features.identity.refresh_session import RefreshSession
from app.features.identity.start_impersonation import StartImpersonation
from app.features.products.capture_product_input_image import CaptureProductInputImage
from app.features.products.complete_input_image_validation import CompleteInputImageValidation
from app.features.products.create_generation_request import CreateGenerationRequest
from app.features.products.create_product import CreateProduct
from app.features.products.create_product_variant import CreateProductVariant
from app.features.products.fan_out_generation_items import FanOutGenerationItems
from app.features.products.list_products import ListProducts
from app.features.products.recompute_product_readiness import RecomputeProductReadiness
from app.features.products.start_input_image_validation import StartInputImageValidation
from app.features.publishing.cancel_publication import CancelPublication
from app.features.publishing.complete_publication_publish import CompletePublicationPublish
from app.features.publishing.create_publication import CreatePublication
from app.features.publishing.defer_publication_publish import DeferPublicationPublish
from app.features.publishing.fail_publication_publish import FailPublicationPublish
from app.features.publishing.release_scheduled_publications import (
    ReleaseScheduledPublicationsForTenant,
)
from app.features.publishing.start_publication_publish import StartPublicationPublish
from app.features.settings.resolve_setting import ResolveSetting
from app.features.settings.upsert_setting import UpsertSetting
from app.features.system.reap_stuck_task_queue_jobs import ReapStuckTaskQueueJobs
from app.features.taxonomy.attach_input_to_catalog_slot import AttachInputToCatalogSlot
from app.features.taxonomy.create_attribute_definition import CreateAttributeDefinition
from app.features.taxonomy.create_catalog_image_slot import CreateCatalogImageSlot
from app.features.taxonomy.create_category import CreateCategory
from app.features.taxonomy.create_input_image_slot import CreateInputImageSlot
from app.features.taxonomy.create_variant_axis import CreateVariantAxis
from app.features.taxonomy.create_variant_axis_value import CreateVariantAxisValue
from app.features.taxonomy.detach_input_from_catalog_slot import DetachInputFromCatalogSlot
from app.features.taxonomy.get_category import GetCategory
from app.features.taxonomy.get_published_category_spec import GetPublishedCategorySpec
from app.features.taxonomy.list_attribute_definitions import ListAttributeDefinitions
from app.features.taxonomy.list_catalog_image_slots import ListCatalogImageSlots
from app.features.taxonomy.list_catalog_slot_input_requirements import (
    ListCatalogSlotInputRequirements,
)
from app.features.taxonomy.list_category_children import ListCategoryChildren
from app.features.taxonomy.list_input_image_slots import ListInputImageSlots
from app.features.taxonomy.list_variant_axes import ListVariantAxes
from app.features.taxonomy.list_variant_axis_values import ListVariantAxisValues
from app.features.taxonomy.move_category import MoveCategory
from app.features.taxonomy.publish_category_spec import PublishCategorySpec
from app.features.taxonomy.update_attribute_definition import UpdateAttributeDefinition
from app.features.taxonomy.update_catalog_image_slot import UpdateCatalogImageSlot
from app.features.taxonomy.update_catalog_slot_input_requirement import (
    UpdateCatalogSlotInputRequirement,
)
from app.features.taxonomy.update_category import UpdateCategory
from app.features.taxonomy.update_input_image_slot import UpdateInputImageSlot
from app.features.taxonomy.update_variant_axis import UpdateVariantAxis
from app.features.taxonomy.update_variant_axis_value import UpdateVariantAxisValue
from app.features.templates.archive_template import ArchiveTemplate
from app.features.templates.complete_template_analysis import CompleteTemplateAnalysis
from app.features.templates.create_authored_template import CreateAuthoredTemplate
from app.features.templates.create_template_from_upload import CreateTemplateFromUpload
from app.features.templates.fail_template_analysis import FailTemplateAnalysis
from app.features.templates.list_templates import ListTemplates
from app.features.templates.seed_stock_presets import SeedStockPresets
from app.features.templates.start_template_analysis import StartTemplateAnalysis
from app.services.ports.channel_publisher import ChannelPublisher
from app.services.ports.content_moderation import ContentModerationScanner
from app.services.ports.identity_provider import IdentityProvider
from app.services.ports.image_generation import ImageGeneration
from app.services.ports.object_storage import ObjectStorage
from app.services.ports.quality_control import QualityControl
from app.services.ports.rate_limiter import RateLimiter
from app.services.ports.text_generation import TextGeneration
from app.services.ports.token_issuer import TokenIssuer
from app.services.ports.unit_of_work import UnitOfWorkFactory
from app.services.ports.vision_analysis import VisionAnalysis
from app.shared.clock import Clock


def get_uow_factory(request: Request) -> UnitOfWorkFactory:
    factory: UnitOfWorkFactory = request.app.state.uow_factory
    return factory


def get_clock(request: Request) -> Clock:
    clock: Clock = request.app.state.clock
    return clock


def get_google_identity_provider(request: Request) -> IdentityProvider:
    provider: IdentityProvider = request.app.state.google_identity_provider
    return provider


UowFactoryDep = Annotated[UnitOfWorkFactory, Depends(get_uow_factory)]
ClockDep = Annotated[Clock, Depends(get_clock)]
GoogleIdentityProviderDep = Annotated[IdentityProvider, Depends(get_google_identity_provider)]


def get_complete_login(
    request: Request,
    provider: GoogleIdentityProviderDep,
    token_issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
    uow_factory: UowFactoryDep,
    clock: ClockDep,
) -> CompleteLogin:
    admin_emails = frozenset(request.app.state.settings.admin_emails)
    return CompleteLogin(
        provider, token_issuer, uow_factory, clock, bootstrap_admin_emails=admin_emails
    )


def get_refresh_session(
    token_issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
    uow_factory: UowFactoryDep,
    clock: ClockDep,
) -> RefreshSession:
    return RefreshSession(token_issuer, uow_factory, clock)


def get_logout(uow_factory: UowFactoryDep, clock: ClockDep) -> Logout:
    return Logout(uow_factory, clock)


def get_start_impersonation(
    token_issuer: Annotated[TokenIssuer, Depends(get_token_issuer)],
    uow_factory: UowFactoryDep,
    clock: ClockDep,
) -> StartImpersonation:
    return StartImpersonation(token_issuer, uow_factory, clock)


CompleteLoginDep = Annotated[CompleteLogin, Depends(get_complete_login)]
RefreshSessionDep = Annotated[RefreshSession, Depends(get_refresh_session)]
LogoutDep = Annotated[Logout, Depends(get_logout)]
StartImpersonationDep = Annotated[StartImpersonation, Depends(get_start_impersonation)]


def get_create_category(uow_factory: UowFactoryDep, clock: ClockDep) -> CreateCategory:
    return CreateCategory(uow_factory, clock)


def get_update_category(uow_factory: UowFactoryDep, clock: ClockDep) -> UpdateCategory:
    return UpdateCategory(uow_factory, clock)


def get_move_category(uow_factory: UowFactoryDep, clock: ClockDep) -> MoveCategory:
    return MoveCategory(uow_factory, clock)


def get_publish_category_spec(uow_factory: UowFactoryDep, clock: ClockDep) -> PublishCategorySpec:
    return PublishCategorySpec(uow_factory, clock)


def get_published_category_spec_use_case(
    uow_factory: UowFactoryDep,
) -> GetPublishedCategorySpec:
    return GetPublishedCategorySpec(uow_factory)


def get_category_use_case(uow_factory: UowFactoryDep) -> GetCategory:
    return GetCategory(uow_factory)


def get_list_category_children(uow_factory: UowFactoryDep) -> ListCategoryChildren:
    return ListCategoryChildren(uow_factory)


def get_create_attribute_definition(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CreateAttributeDefinition:
    return CreateAttributeDefinition(uow_factory, clock)


def get_update_attribute_definition(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> UpdateAttributeDefinition:
    return UpdateAttributeDefinition(uow_factory, clock)


def get_list_attribute_definitions(uow_factory: UowFactoryDep) -> ListAttributeDefinitions:
    return ListAttributeDefinitions(uow_factory)


def get_create_variant_axis(uow_factory: UowFactoryDep, clock: ClockDep) -> CreateVariantAxis:
    return CreateVariantAxis(uow_factory, clock)


def get_update_variant_axis(uow_factory: UowFactoryDep, clock: ClockDep) -> UpdateVariantAxis:
    return UpdateVariantAxis(uow_factory, clock)


def get_list_variant_axes(uow_factory: UowFactoryDep) -> ListVariantAxes:
    return ListVariantAxes(uow_factory)


def get_create_variant_axis_value(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CreateVariantAxisValue:
    return CreateVariantAxisValue(uow_factory, clock)


def get_update_variant_axis_value(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> UpdateVariantAxisValue:
    return UpdateVariantAxisValue(uow_factory, clock)


def get_list_variant_axis_values(uow_factory: UowFactoryDep) -> ListVariantAxisValues:
    return ListVariantAxisValues(uow_factory)


def get_create_input_image_slot(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CreateInputImageSlot:
    return CreateInputImageSlot(uow_factory, clock)


def get_update_input_image_slot(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> UpdateInputImageSlot:
    return UpdateInputImageSlot(uow_factory, clock)


def get_list_input_image_slots(uow_factory: UowFactoryDep) -> ListInputImageSlots:
    return ListInputImageSlots(uow_factory)


def get_create_catalog_image_slot(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CreateCatalogImageSlot:
    return CreateCatalogImageSlot(uow_factory, clock)


def get_update_catalog_image_slot(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> UpdateCatalogImageSlot:
    return UpdateCatalogImageSlot(uow_factory, clock)


def get_list_catalog_image_slots(uow_factory: UowFactoryDep) -> ListCatalogImageSlots:
    return ListCatalogImageSlots(uow_factory)


def get_attach_input_to_catalog_slot(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> AttachInputToCatalogSlot:
    return AttachInputToCatalogSlot(uow_factory, clock)


def get_update_catalog_slot_input_requirement(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> UpdateCatalogSlotInputRequirement:
    return UpdateCatalogSlotInputRequirement(uow_factory, clock)


def get_detach_input_from_catalog_slot(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> DetachInputFromCatalogSlot:
    return DetachInputFromCatalogSlot(uow_factory, clock)


def get_list_catalog_slot_input_requirements(
    uow_factory: UowFactoryDep,
) -> ListCatalogSlotInputRequirements:
    return ListCatalogSlotInputRequirements(uow_factory)


def get_upsert_setting(uow_factory: UowFactoryDep, clock: ClockDep) -> UpsertSetting:
    return UpsertSetting(uow_factory, clock)


def get_resolve_setting(uow_factory: UowFactoryDep) -> ResolveSetting:
    return ResolveSetting(uow_factory)


def get_request_upload(
    object_storage: Annotated[ObjectStorage, Depends(get_object_storage)], clock: ClockDep
) -> RequestUpload:
    return RequestUpload(object_storage, clock)


def get_request_download(
    uow_factory: UowFactoryDep,
    object_storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    clock: ClockDep,
) -> RequestDownload:
    return RequestDownload(uow_factory, object_storage, clock)


def get_verify_and_register_upload(
    uow_factory: UowFactoryDep,
    object_storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    moderation_scanner: Annotated[
        ContentModerationScanner, Depends(get_content_moderation_scanner)
    ],
    clock: ClockDep,
) -> VerifyAndRegisterUpload:
    return VerifyAndRegisterUpload(uow_factory, object_storage, moderation_scanner, clock)


def get_create_authored_template(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CreateAuthoredTemplate:
    return CreateAuthoredTemplate(uow_factory, clock)


def get_create_template_from_upload(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CreateTemplateFromUpload:
    return CreateTemplateFromUpload(uow_factory, clock)


def get_list_templates(uow_factory: UowFactoryDep) -> ListTemplates:
    return ListTemplates(uow_factory)


def get_archive_template(uow_factory: UowFactoryDep, clock: ClockDep) -> ArchiveTemplate:
    return ArchiveTemplate(uow_factory, clock)


def get_seed_stock_presets(uow_factory: UowFactoryDep, clock: ClockDep) -> SeedStockPresets:
    return SeedStockPresets(uow_factory, clock)


def get_recompute_product_readiness(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> RecomputeProductReadiness:
    return RecomputeProductReadiness(uow_factory, clock)


def get_create_product(uow_factory: UowFactoryDep, clock: ClockDep) -> CreateProduct:
    return CreateProduct(uow_factory, clock)


def get_create_product_variant(uow_factory: UowFactoryDep, clock: ClockDep) -> CreateProductVariant:
    return CreateProductVariant(uow_factory, clock)


def get_capture_product_input_image(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CaptureProductInputImage:
    return CaptureProductInputImage(uow_factory, clock)


def get_list_products(uow_factory: UowFactoryDep) -> ListProducts:
    return ListProducts(uow_factory)


def get_create_generation_request(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CreateGenerationRequest:
    return CreateGenerationRequest(uow_factory, clock)


def get_fan_out_generation_items(
    request: Request, uow_factory: UowFactoryDep, clock: ClockDep
) -> FanOutGenerationItems:
    settings = request.app.state.settings
    return FanOutGenerationItems(
        uow_factory,
        clock,
        provider=settings.generation_provider,
        model=settings.generation_model,
    )


def get_start_input_image_validation(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> StartInputImageValidation:
    return StartInputImageValidation(uow_factory, clock)


def get_complete_input_image_validation(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CompleteInputImageValidation:
    return CompleteInputImageValidation(uow_factory, clock)


def get_input_image_validation_agent(
    start: Annotated[StartInputImageValidation, Depends(get_start_input_image_validation)],
    complete: Annotated[CompleteInputImageValidation, Depends(get_complete_input_image_validation)],
    object_storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> InputImageValidationAgent:
    return InputImageValidationAgent(start, complete, object_storage)


def get_start_template_analysis(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> StartTemplateAnalysis:
    return StartTemplateAnalysis(uow_factory, clock)


def get_complete_template_analysis(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CompleteTemplateAnalysis:
    return CompleteTemplateAnalysis(uow_factory, clock)


def get_fail_template_analysis(uow_factory: UowFactoryDep, clock: ClockDep) -> FailTemplateAnalysis:
    return FailTemplateAnalysis(uow_factory, clock)


def get_template_analysis_agent(
    start: Annotated[StartTemplateAnalysis, Depends(get_start_template_analysis)],
    complete: Annotated[CompleteTemplateAnalysis, Depends(get_complete_template_analysis)],
    fail: Annotated[FailTemplateAnalysis, Depends(get_fail_template_analysis)],
    object_storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    vision_analysis: Annotated[VisionAnalysis, Depends(get_vision_analysis)],
) -> TemplateAnalysisAgent:
    return TemplateAnalysisAgent(start, complete, fail, object_storage, vision_analysis)


def get_start_generation_item_render(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> StartGenerationItemRender:
    return StartGenerationItemRender(uow_factory, clock)


def get_complete_generation_item_render(
    uow_factory: UowFactoryDep,
    clock: ClockDep,
    object_storage: Annotated[ObjectStorage, Depends(get_object_storage)],
) -> CompleteGenerationItemRender:
    return CompleteGenerationItemRender(uow_factory, object_storage, clock)


def get_fail_generation_item_render(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> FailGenerationItemRender:
    return FailGenerationItemRender(uow_factory, clock)


def get_generation_render_agent(
    start: Annotated[StartGenerationItemRender, Depends(get_start_generation_item_render)],
    complete: Annotated[CompleteGenerationItemRender, Depends(get_complete_generation_item_render)],
    fail: Annotated[FailGenerationItemRender, Depends(get_fail_generation_item_render)],
    object_storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    image_generation: Annotated[ImageGeneration, Depends(get_image_generation)],
) -> GenerationRenderAgent:
    return GenerationRenderAgent(start, complete, fail, object_storage, image_generation)


def get_start_catalog_image_qc(uow_factory: UowFactoryDep, clock: ClockDep) -> StartCatalogImageQc:
    return StartCatalogImageQc(uow_factory, clock)


def get_complete_catalog_image_qc(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CompleteCatalogImageQc:
    return CompleteCatalogImageQc(uow_factory, clock)


def get_fail_catalog_image_qc(uow_factory: UowFactoryDep, clock: ClockDep) -> FailCatalogImageQc:
    return FailCatalogImageQc(uow_factory, clock)


def get_catalog_image_qc_agent(
    start: Annotated[StartCatalogImageQc, Depends(get_start_catalog_image_qc)],
    complete: Annotated[CompleteCatalogImageQc, Depends(get_complete_catalog_image_qc)],
    fail: Annotated[FailCatalogImageQc, Depends(get_fail_catalog_image_qc)],
    object_storage: Annotated[ObjectStorage, Depends(get_object_storage)],
    quality_control: Annotated[QualityControl, Depends(get_quality_control)],
) -> CatalogImageQcAgent:
    return CatalogImageQcAgent(start, complete, fail, object_storage, quality_control)


def get_approve_catalog_image(uow_factory: UowFactoryDep, clock: ClockDep) -> ApproveCatalogImage:
    return ApproveCatalogImage(uow_factory, clock)


def get_reject_catalog_image(uow_factory: UowFactoryDep, clock: ClockDep) -> RejectCatalogImage:
    return RejectCatalogImage(uow_factory, clock)


def get_list_catalog_images_for_review(
    uow_factory: UowFactoryDep,
) -> ListCatalogImagesForReview:
    return ListCatalogImagesForReview(uow_factory)


def get_bulk_approve_catalog_images_for_product(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> BulkApproveCatalogImagesForProduct:
    return BulkApproveCatalogImagesForProduct(uow_factory, clock)


def get_generate_content_draft(
    request: Request, uow_factory: UowFactoryDep, clock: ClockDep
) -> GenerateContentDraft:
    settings = request.app.state.settings
    return GenerateContentDraft(uow_factory, clock, model=settings.content_generation_model)


def get_start_content_draft_generation(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> StartContentDraftGeneration:
    return StartContentDraftGeneration(uow_factory, clock)


def get_complete_content_draft_generation(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CompleteContentDraftGeneration:
    return CompleteContentDraftGeneration(uow_factory, clock)


def get_fail_content_draft_generation(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> FailContentDraftGeneration:
    return FailContentDraftGeneration(uow_factory, clock)


def get_copywriting_agent(
    start: Annotated[StartContentDraftGeneration, Depends(get_start_content_draft_generation)],
    complete: Annotated[
        CompleteContentDraftGeneration, Depends(get_complete_content_draft_generation)
    ],
    fail: Annotated[FailContentDraftGeneration, Depends(get_fail_content_draft_generation)],
    text_generation: Annotated[TextGeneration, Depends(get_text_generation)],
) -> CopywritingAgent:
    return CopywritingAgent(start, complete, fail, text_generation)


def get_create_publication(uow_factory: UowFactoryDep, clock: ClockDep) -> CreatePublication:
    return CreatePublication(uow_factory, clock)


def get_start_publication_publish(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> StartPublicationPublish:
    return StartPublicationPublish(uow_factory, clock)


def get_complete_publication_publish(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> CompletePublicationPublish:
    return CompletePublicationPublish(uow_factory, clock)


def get_fail_publication_publish(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> FailPublicationPublish:
    return FailPublicationPublish(uow_factory, clock)


def get_defer_publication_publish(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> DeferPublicationPublish:
    return DeferPublicationPublish(uow_factory, clock)


def get_release_scheduled_publications_for_tenant(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> ReleaseScheduledPublicationsForTenant:
    return ReleaseScheduledPublicationsForTenant(uow_factory, clock)


def get_cancel_publication(uow_factory: UowFactoryDep, clock: ClockDep) -> CancelPublication:
    return CancelPublication(uow_factory, clock)


def get_publish_channel_agent(
    request: Request,
    start: Annotated[StartPublicationPublish, Depends(get_start_publication_publish)],
    complete: Annotated[CompletePublicationPublish, Depends(get_complete_publication_publish)],
    fail: Annotated[FailPublicationPublish, Depends(get_fail_publication_publish)],
    defer: Annotated[DeferPublicationPublish, Depends(get_defer_publication_publish)],
    channel_publisher: Annotated[ChannelPublisher, Depends(get_channel_publisher)],
    rate_limiter: Annotated[RateLimiter, Depends(get_rate_limiter)],
    clock: ClockDep,
) -> PublishChannelAgent:
    settings = request.app.state.settings
    return PublishChannelAgent(
        start,
        complete,
        fail,
        defer,
        channel_publisher,
        rate_limiter,
        clock,
        rate_limit_per_account_per_day=settings.publish_rate_limit_per_account_per_day,
    )


def get_approve_content_draft(uow_factory: UowFactoryDep, clock: ClockDep) -> ApproveContentDraft:
    return ApproveContentDraft(uow_factory, clock)


def get_reject_content_draft(uow_factory: UowFactoryDep, clock: ClockDep) -> RejectContentDraft:
    return RejectContentDraft(uow_factory, clock)


def get_list_content_drafts_for_variant(
    uow_factory: UowFactoryDep,
) -> ListContentDraftsForVariant:
    return ListContentDraftsForVariant(uow_factory)


def get_edit_content_draft(uow_factory: UowFactoryDep, clock: ClockDep) -> EditContentDraft:
    return EditContentDraft(uow_factory, clock)


def get_reap_stuck_task_queue_jobs(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> ReapStuckTaskQueueJobs:
    return ReapStuckTaskQueueJobs(uow_factory, clock)


def get_reconcile_generation_requests_for_tenant(
    uow_factory: UowFactoryDep, clock: ClockDep
) -> ReconcileGenerationRequestsForTenant:
    return ReconcileGenerationRequestsForTenant(uow_factory, clock)


CreateCategoryDep = Annotated[CreateCategory, Depends(get_create_category)]
UpdateCategoryDep = Annotated[UpdateCategory, Depends(get_update_category)]
MoveCategoryDep = Annotated[MoveCategory, Depends(get_move_category)]
PublishCategorySpecDep = Annotated[PublishCategorySpec, Depends(get_publish_category_spec)]
GetPublishedCategorySpecDep = Annotated[
    GetPublishedCategorySpec, Depends(get_published_category_spec_use_case)
]
GetCategoryDep = Annotated[GetCategory, Depends(get_category_use_case)]
ListCategoryChildrenDep = Annotated[ListCategoryChildren, Depends(get_list_category_children)]
CreateAttributeDefinitionDep = Annotated[
    CreateAttributeDefinition, Depends(get_create_attribute_definition)
]
UpdateAttributeDefinitionDep = Annotated[
    UpdateAttributeDefinition, Depends(get_update_attribute_definition)
]
ListAttributeDefinitionsDep = Annotated[
    ListAttributeDefinitions, Depends(get_list_attribute_definitions)
]
CreateVariantAxisDep = Annotated[CreateVariantAxis, Depends(get_create_variant_axis)]
UpdateVariantAxisDep = Annotated[UpdateVariantAxis, Depends(get_update_variant_axis)]
ListVariantAxesDep = Annotated[ListVariantAxes, Depends(get_list_variant_axes)]
CreateVariantAxisValueDep = Annotated[
    CreateVariantAxisValue, Depends(get_create_variant_axis_value)
]
UpdateVariantAxisValueDep = Annotated[
    UpdateVariantAxisValue, Depends(get_update_variant_axis_value)
]
ListVariantAxisValuesDep = Annotated[ListVariantAxisValues, Depends(get_list_variant_axis_values)]
CreateInputImageSlotDep = Annotated[CreateInputImageSlot, Depends(get_create_input_image_slot)]
UpdateInputImageSlotDep = Annotated[UpdateInputImageSlot, Depends(get_update_input_image_slot)]
ListInputImageSlotsDep = Annotated[ListInputImageSlots, Depends(get_list_input_image_slots)]
CreateCatalogImageSlotDep = Annotated[
    CreateCatalogImageSlot, Depends(get_create_catalog_image_slot)
]
UpdateCatalogImageSlotDep = Annotated[
    UpdateCatalogImageSlot, Depends(get_update_catalog_image_slot)
]
ListCatalogImageSlotsDep = Annotated[ListCatalogImageSlots, Depends(get_list_catalog_image_slots)]
AttachInputToCatalogSlotDep = Annotated[
    AttachInputToCatalogSlot, Depends(get_attach_input_to_catalog_slot)
]
UpdateCatalogSlotInputRequirementDep = Annotated[
    UpdateCatalogSlotInputRequirement, Depends(get_update_catalog_slot_input_requirement)
]
DetachInputFromCatalogSlotDep = Annotated[
    DetachInputFromCatalogSlot, Depends(get_detach_input_from_catalog_slot)
]
ListCatalogSlotInputRequirementsDep = Annotated[
    ListCatalogSlotInputRequirements, Depends(get_list_catalog_slot_input_requirements)
]
UpsertSettingDep = Annotated[UpsertSetting, Depends(get_upsert_setting)]
ResolveSettingDep = Annotated[ResolveSetting, Depends(get_resolve_setting)]
RequestUploadDep = Annotated[RequestUpload, Depends(get_request_upload)]
RequestDownloadDep = Annotated[RequestDownload, Depends(get_request_download)]
VerifyAndRegisterUploadDep = Annotated[
    VerifyAndRegisterUpload, Depends(get_verify_and_register_upload)
]
CreateAuthoredTemplateDep = Annotated[CreateAuthoredTemplate, Depends(get_create_authored_template)]
CreateTemplateFromUploadDep = Annotated[
    CreateTemplateFromUpload, Depends(get_create_template_from_upload)
]
ListTemplatesDep = Annotated[ListTemplates, Depends(get_list_templates)]
ArchiveTemplateDep = Annotated[ArchiveTemplate, Depends(get_archive_template)]
SeedStockPresetsDep = Annotated[SeedStockPresets, Depends(get_seed_stock_presets)]
RecomputeProductReadinessDep = Annotated[
    RecomputeProductReadiness, Depends(get_recompute_product_readiness)
]
CreateProductDep = Annotated[CreateProduct, Depends(get_create_product)]
CreateProductVariantDep = Annotated[CreateProductVariant, Depends(get_create_product_variant)]
CaptureProductInputImageDep = Annotated[
    CaptureProductInputImage, Depends(get_capture_product_input_image)
]
ListProductsDep = Annotated[ListProducts, Depends(get_list_products)]
CreateGenerationRequestDep = Annotated[
    CreateGenerationRequest, Depends(get_create_generation_request)
]
FanOutGenerationItemsDep = Annotated[FanOutGenerationItems, Depends(get_fan_out_generation_items)]
InputImageValidationAgentDep = Annotated[
    InputImageValidationAgent, Depends(get_input_image_validation_agent)
]
TemplateAnalysisAgentDep = Annotated[TemplateAnalysisAgent, Depends(get_template_analysis_agent)]
GenerationRenderAgentDep = Annotated[GenerationRenderAgent, Depends(get_generation_render_agent)]
CatalogImageQcAgentDep = Annotated[CatalogImageQcAgent, Depends(get_catalog_image_qc_agent)]
ReapStuckTaskQueueJobsDep = Annotated[
    ReapStuckTaskQueueJobs, Depends(get_reap_stuck_task_queue_jobs)
]
ReconcileGenerationRequestsForTenantDep = Annotated[
    ReconcileGenerationRequestsForTenant, Depends(get_reconcile_generation_requests_for_tenant)
]
ApproveCatalogImageDep = Annotated[ApproveCatalogImage, Depends(get_approve_catalog_image)]
RejectCatalogImageDep = Annotated[RejectCatalogImage, Depends(get_reject_catalog_image)]
ListCatalogImagesForReviewDep = Annotated[
    ListCatalogImagesForReview, Depends(get_list_catalog_images_for_review)
]
BulkApproveCatalogImagesForProductDep = Annotated[
    BulkApproveCatalogImagesForProduct, Depends(get_bulk_approve_catalog_images_for_product)
]
GenerateContentDraftDep = Annotated[GenerateContentDraft, Depends(get_generate_content_draft)]
CopywritingAgentDep = Annotated[CopywritingAgent, Depends(get_copywriting_agent)]
CreatePublicationDep = Annotated[CreatePublication, Depends(get_create_publication)]
PublishChannelAgentDep = Annotated[PublishChannelAgent, Depends(get_publish_channel_agent)]
ReleaseScheduledPublicationsForTenantDep = Annotated[
    ReleaseScheduledPublicationsForTenant,
    Depends(get_release_scheduled_publications_for_tenant),
]
CancelPublicationDep = Annotated[CancelPublication, Depends(get_cancel_publication)]
ApproveContentDraftDep = Annotated[ApproveContentDraft, Depends(get_approve_content_draft)]
RejectContentDraftDep = Annotated[RejectContentDraft, Depends(get_reject_content_draft)]
ListContentDraftsForVariantDep = Annotated[
    ListContentDraftsForVariant, Depends(get_list_content_drafts_for_variant)
]
EditContentDraftDep = Annotated[EditContentDraft, Depends(get_edit_content_draft)]
