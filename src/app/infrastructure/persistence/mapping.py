"""Imperative ORM mapping (D7): the first in this codebase.

Domain entities in ``app.entities`` are plain dataclasses with zero knowledge
of SQLAlchemy. The ``Table`` objects and ``registry.map_imperatively(...)``
calls here are what makes them persistable — one class per concept, no
parallel ORM model, no hand-written row-to-entity mapper to maintain.

Column shapes here are hand-kept in sync with the Alembic migrations that
created them (no ``autogenerate`` yet — see ``migrations/env.py``). They do
not need to restate every DB-level constraint (CHECK constraints, for
instance) since Postgres enforces those regardless of what SQLAlchemy knows;
they need to be accurate enough for correct query generation.

Enum-typed entity fields (``TenantMembership.role: Role``) use SQLAlchemy's
``Enum(..., native_enum=False, values_callable=...)`` on the Column, not a
plain ``Text`` column with manual conversion at the repository boundary.
That was the first draft, and it does not actually work: with
``map_imperatively`` binding the entity class itself, the ORM sets attributes
directly from row values with no conversion step unless the Column type
provides one. A plain-Text column round-trips a ``Role`` correctly on
*write* only because ``Role(str, Enum)`` members are themselves ``str``
instances — but a *read* sets ``.role`` to a bare ``str`` such as
``"owner"``, and a bare ``str`` has no ``.value`` attribute, so any code
calling ``membership.role.value`` after a read crashes. Confirmed with a
throwaway script before writing this, not assumed. ``values_callable`` is
required alongside ``native_enum=False`` — SQLAlchemy's default is to store
the enum *member name*, not ``.value``, which would not match this schema's
lowercase values or its ``CHECK`` constraint.

``start_mappers()`` is called exactly once, from the composition root
(``bootstrap``), before any session is created. Calling it twice raises —
SQLAlchemy does not support re-mapping a class.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Table,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import ARRAY, INET, JSONB
from sqlalchemy.orm import registry

from app.entities.asset import Asset, AssetKind
from app.entities.attribute_definition import AttributeDataType, AttributeDefinition, SemanticRole
from app.entities.catalog_image import CatalogImage, CatalogImageStatus
from app.entities.catalog_slot_input_requirement import CatalogSlotInputRequirement
from app.entities.catalog_template import CatalogTemplate, TemplateKind, TemplateStatus
from app.entities.category import Category
from app.entities.category_spec_version import CategorySpecVersion, SpecVersionStatus
from app.entities.generation_item import GenerationItem, GenerationItemStatus
from app.entities.generation_request import GenerationRequest, GenerationRequestStatus
from app.entities.identity import Identity
from app.entities.image_slots import CatalogImageSlot, InputImageSlot
from app.entities.product import Product, ProductStatus
from app.entities.product_input_image import InputImageStatus, ProductInputImage
from app.entities.product_variant import ProductVariant
from app.entities.roles import Role
from app.entities.session import Session
from app.entities.setting import Setting, SettingScope
from app.entities.tenant_membership import TenantMembership
from app.entities.user import User
from app.entities.variant_axis import VariantAxis, VariantAxisValue

_role_type = Enum(
    Role,
    name="tenant_membership_role",
    native_enum=False,  # stored as text + a CHECK constraint (the migration), not a PG enum type
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

_data_type_type = Enum(
    AttributeDataType,
    name="attribute_definition_data_type",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

_semantic_role_type = Enum(
    SemanticRole,
    name="attribute_definition_semantic_role",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

_spec_version_status_type = Enum(
    SpecVersionStatus,
    name="category_spec_version_status",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

_setting_scope_type = Enum(
    SettingScope,
    name="setting_scope_type",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

_asset_kind_type = Enum(
    AssetKind,
    name="asset_kind",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

_template_kind_type = Enum(
    TemplateKind,
    name="catalog_template_kind",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

_template_status_type = Enum(
    TemplateStatus,
    name="catalog_template_status",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

_product_status_type = Enum(
    ProductStatus,
    name="product_status",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

_input_image_status_type = Enum(
    InputImageStatus,
    name="product_input_image_status",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

_generation_request_status_type = Enum(
    GenerationRequestStatus,
    name="generation_request_status",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

_generation_item_status_type = Enum(
    GenerationItemStatus,
    name="generation_item_status",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

_catalog_image_status_type = Enum(
    CatalogImageStatus,
    name="catalog_image_status",
    native_enum=False,
    values_callable=lambda enum_cls: [member.value for member in enum_cls],
    validate_strings=True,
)

mapper_registry = registry()
metadata = mapper_registry.metadata

# No entity class - a platform-plane row, not a rich domain object (D4);
# ``tenants`` carries no RLS (see the bootstrap migration's docstring), so
# reading across every tenant is a legitimate query here, unlike every
# tenant-scoped table below. Queried via Core directly by
# ``SqlTenantRepository``.
tenants_table = Table(
    "tenants",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("name", Text(), nullable=False),
    Column("slug", Text(), nullable=False, unique=True),
    Column("status", Text(), nullable=False),
    Column("plan", Text(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

users_table = Table(
    "users",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("email", Text(), nullable=False),
    Column("email_verified", Boolean(), nullable=False),
    Column("display_name", Text(), nullable=True),
    Column("status", Text(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

identities_table = Table(
    "identities",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("user_id", ForeignKey("users.id"), nullable=False),
    Column("provider", Text(), nullable=False),
    Column("issuer", Text(), nullable=False),
    Column("subject", Text(), nullable=False),
    Column("raw_claims", JSONB(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

tenant_memberships_table = Table(
    "tenant_memberships",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("user_id", ForeignKey("users.id"), nullable=False),
    Column("role", _role_type, nullable=False),
    Column("extra_capabilities", JSONB(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

sessions_table = Table(
    "sessions",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("user_id", ForeignKey("users.id"), nullable=False),
    Column("tenant_id", Uuid(), nullable=True),
    Column("refresh_token_hash", Text(), nullable=False),
    Column("previous_token_hash", Text(), nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# No entity class - an append-only log row, not a rich domain object.
# Queried via Core directly by SqlAuditLogRepository. Table created in
# ca5759119d91 (chunk 3); this is the first repository built for it.
audit_log_table = Table(
    "audit_log",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("actor_user_id", Uuid(), nullable=True),
    Column("action", Text(), nullable=False),
    Column("subject_type", Text(), nullable=False),
    Column("subject_id", Uuid(), nullable=False),
    Column("before", JSONB(), nullable=True),
    Column("after", JSONB(), nullable=True),
    Column("ip", INET(), nullable=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)

categories_table = Table(
    "categories",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("parent_id", Uuid(), nullable=True),
    Column("path", Text(), nullable=False),
    Column("depth", Integer(), nullable=False),
    Column("key", Text(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("slug", Text(), nullable=False),
    Column("description", Text(), nullable=True),
    Column("position", Integer(), nullable=False),
    Column("is_active", Boolean(), nullable=False),
    Column("current_spec_version", Integer(), nullable=True),
    Column("draft_spec_version", Integer(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

attribute_definitions_table = Table(
    "attribute_definitions",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("category_id", Uuid(), nullable=False),
    Column("key", Text(), nullable=False),
    Column("label", Text(), nullable=False),
    Column("help_text", Text(), nullable=True),
    Column("data_type", _data_type_type, nullable=False),
    Column("semantic_role", _semantic_role_type, nullable=True),
    Column("is_required", Boolean(), nullable=False),
    Column("is_filterable", Boolean(), nullable=False),
    Column("is_public", Boolean(), nullable=False),
    Column("position", Integer(), nullable=False),
    Column("validation", JSONB(), nullable=False),
    Column("ui", JSONB(), nullable=False),
    Column("default_value", JSONB(), nullable=True),
    Column("introduced_in_version", Integer(), nullable=True),
    Column("retired_in_version", Integer(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

variant_axes_table = Table(
    "variant_axes",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("category_id", Uuid(), nullable=False),
    Column("key", Text(), nullable=False),
    Column("label", Text(), nullable=False),
    Column("position", Integer(), nullable=False),
    Column("affects_imagery", Boolean(), nullable=False),
    Column("introduced_in_version", Integer(), nullable=True),
    Column("retired_in_version", Integer(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

variant_axis_values_table = Table(
    "variant_axis_values",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("axis_id", Uuid(), nullable=False),
    Column("value", Text(), nullable=False),
    Column("label", Text(), nullable=False),
    Column("metadata", JSONB(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

input_image_slots_table = Table(
    "input_image_slots",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("category_id", Uuid(), nullable=False),
    Column("key", Text(), nullable=False),
    Column("label", Text(), nullable=False),
    Column("description", Text(), nullable=True),
    Column("capture_guidance", Text(), nullable=True),
    Column("example_asset_id", Uuid(), nullable=True),
    Column("normalisation", JSONB(), nullable=False),
    Column("is_required", Boolean(), nullable=False),
    Column("position", Integer(), nullable=False),
    Column("introduced_in_version", Integer(), nullable=True),
    Column("retired_in_version", Integer(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

catalog_image_slots_table = Table(
    "catalog_image_slots",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("category_id", Uuid(), nullable=False),
    Column("key", Text(), nullable=False),
    Column("label", Text(), nullable=False),
    Column("description", Text(), nullable=True),
    Column("position", Integer(), nullable=False),
    Column("aspect_ratio", Text(), nullable=False),
    Column("target_width", Integer(), nullable=False),
    Column("target_height", Integer(), nullable=False),
    Column("is_required", Boolean(), nullable=False),
    Column("introduced_in_version", Integer(), nullable=True),
    Column("retired_in_version", Integer(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

catalog_slot_input_requirements_table = Table(
    "catalog_slot_input_requirements",
    metadata,
    Column("catalog_image_slot_id", Uuid(), primary_key=True),
    Column("input_image_slot_id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("role", Text(), nullable=False),
    Column("prompt_position", Integer(), nullable=False),
    Column("is_required", Boolean(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

category_spec_versions_table = Table(
    "category_spec_versions",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("category_id", Uuid(), nullable=False),
    Column("version", Integer(), nullable=False),
    Column("status", _spec_version_status_type, nullable=False),
    Column("snapshot", JSONB(), nullable=False),
    Column("change_summary", JSONB(), nullable=True),
    Column("published_by", Uuid(), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=False),
)

settings_table = Table(
    "settings",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=True),
    Column("scope_type", _setting_scope_type, nullable=False),
    Column("scope_id", Uuid(), nullable=True),
    Column("key", Text(), nullable=False),
    Column("value", JSONB(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

assets_table = Table(
    "assets",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("storage_key", Text(), nullable=False),
    Column("sha256", Text(), nullable=False),
    Column("mime", Text(), nullable=False),
    Column("width", Integer(), nullable=False),
    Column("height", Integer(), nullable=False),
    Column("bytes", BigInteger(), nullable=False),
    Column("kind", _asset_kind_type, nullable=False),
    Column("source", Text(), nullable=False),
    Column("parent_asset_id", Uuid(), nullable=True),
    Column("meta", JSONB(), nullable=False),
    Column("uploaded_by", Uuid(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

catalog_templates_table = Table(
    "catalog_templates",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("catalog_image_slot_id", Uuid(), nullable=False),
    Column("name", Text(), nullable=False),
    Column("version", Integer(), nullable=False),
    Column("is_default", Boolean(), nullable=False),
    Column("position", Integer(), nullable=False),
    Column("kind", _template_kind_type, nullable=False),
    Column("source_asset_id", Uuid(), nullable=True),
    Column("status", _template_status_type, nullable=False),
    Column("analysis", JSONB(), nullable=True),
    Column("prompt_template", Text(), nullable=True),
    Column("prompt_version", Integer(), nullable=True),
    Column("analysis_model", Text(), nullable=True),
    Column("analysed_at", DateTime(timezone=True), nullable=True),
    Column("analysis_error", Text(), nullable=True),
    Column("created_by", Uuid(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

products_table = Table(
    "products",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("category_id", Uuid(), nullable=False),
    Column("spec_version_id", Uuid(), nullable=False),
    Column("attributes", JSONB(), nullable=False),
    Column("title", Text(), nullable=True),
    Column("sku", Text(), nullable=True),
    Column("price_amount", BigInteger(), nullable=True),
    Column("price_currency", Text(), nullable=True),
    Column("status", _product_status_type, nullable=False),
    Column("created_by", Uuid(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

product_variants_table = Table(
    "product_variants",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("product_id", Uuid(), nullable=False),
    Column("sku", Text(), nullable=True),
    Column("axis_values", JSONB(), nullable=False),
    Column("attributes", JSONB(), nullable=False),
    Column("status", _product_status_type, nullable=False),
    Column("is_default", Boolean(), nullable=False),
    Column("position", Integer(), nullable=False),
    Column("created_by", Uuid(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

product_input_images_table = Table(
    "product_input_images",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("product_id", Uuid(), nullable=False),
    Column("variant_id", Uuid(), nullable=True),
    Column("input_image_slot_id", Uuid(), nullable=False),
    Column("asset_id", Uuid(), nullable=False),
    Column("normalised_asset_id", Uuid(), nullable=True),
    Column("status", _input_image_status_type, nullable=False),
    Column("rejection_reason", Text(), nullable=True),
    Column("created_by", Uuid(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

generation_requests_table = Table(
    "generation_requests",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("product_id", Uuid(), nullable=False),
    Column("variant_id", Uuid(), nullable=False),
    Column("spec_version_id", Uuid(), nullable=False),
    Column("status", _generation_request_status_type, nullable=False),
    Column("settings_snapshot", JSONB(), nullable=False),
    Column("quota_reservation_id", Uuid(), nullable=True),
    Column("requested_by", Uuid(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("completed_at", DateTime(timezone=True), nullable=True),
)

generation_items_table = Table(
    "generation_items",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("request_id", Uuid(), nullable=False),
    Column("catalog_image_slot_id", Uuid(), nullable=False),
    Column("template_id", Uuid(), nullable=False),
    Column("attempt_no", Integer(), nullable=False),
    Column("status", _generation_item_status_type, nullable=False),
    Column("provider", Text(), nullable=False),
    Column("model", Text(), nullable=False),
    Column("model_params", JSONB(), nullable=False),
    Column("seed", BigInteger(), nullable=False),
    Column("prompt_rendered", Text(), nullable=False),
    Column("prompt_version", Text(), nullable=False),
    Column("input_asset_ids", ARRAY(Uuid()), nullable=False),
    Column("output_asset_id", Uuid(), nullable=True),
    Column("cost_micros", BigInteger(), nullable=True),
    Column("latency_ms", Integer(), nullable=True),
    Column("error_code", Text(), nullable=True),
    Column("error_detail", Text(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

catalog_images_table = Table(
    "catalog_images",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("variant_id", Uuid(), nullable=False),
    Column("catalog_image_slot_id", Uuid(), nullable=False),
    Column("asset_id", Uuid(), nullable=False),
    Column("generation_item_id", Uuid(), nullable=False),
    Column("status", _catalog_image_status_type, nullable=False),
    Column("qc_result", JSONB(), nullable=True),
    Column("is_primary", Boolean(), nullable=False),
    Column("approved_by", Uuid(), nullable=True),
    Column("approved_at", DateTime(timezone=True), nullable=True),
    Column("rejection_reason", Text(), nullable=True),
    Column("superseded_by", Uuid(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# No entity class - a grant, not a rich domain object. Queried via Core
# directly by SqlPlatformAdminRepository rather than through the ORM.
platform_admins_table = Table(
    "platform_admins",
    metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("granted_by", ForeignKey("users.id"), nullable=False),
    Column("granted_at", DateTime(timezone=True), nullable=False),
)

# No entity class - a stored claim ticket, not a rich domain object. Queried
# via Core directly by SqlIdempotencyRepository, same shape as
# platform_admins_table above.
idempotency_keys_table = Table(
    "idempotency_keys",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("key", Text(), nullable=False),
    Column("request_fingerprint", Text(), nullable=False),
    # Both null between reserve() and store_response() - see the port's
    # module docstring for why that gap is a legitimate, distinguishable
    # state rather than something to collapse into one write.
    Column("response_status", Integer(), nullable=True),
    Column("response_body", JSONB(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

# No entity class - a stored delivery ticket, not a rich domain object.
# Queried via Core directly by SqlOutboxEventRepository, same shape as
# idempotency_keys_table above.
outbox_events_table = Table(
    "outbox_events",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("event_type", Text(), nullable=False),
    Column("payload", JSONB(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=True),
)

# No entity class - a queue row, not a rich domain object. Queried via Core
# directly by SqlTaskQueue, same shape as outbox_events_table above.
task_queue_jobs_table = Table(
    "task_queue_jobs",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("job_type", Text(), nullable=False),
    Column("payload", JSONB(), nullable=False),
    Column("status", Text(), nullable=False),
    Column("attempts", Integer(), nullable=False),
    Column("max_attempts", Integer(), nullable=False),
    Column("run_at", DateTime(timezone=True), nullable=False),
    Column("claimed_at", DateTime(timezone=True), nullable=True),
    Column("claimed_by", Text(), nullable=True),
    Column("last_error", Text(), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# No entity class - a counter, not a rich domain object (D24). Queried via
# Core directly by SqlQuotaReservationRepository.
quota_reservations_table = Table(
    "quota_reservations",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("period", Text(), nullable=False),
    Column("metric", Text(), nullable=False),
    Column("limit_value", Integer(), nullable=False),
    Column("reserved", Integer(), nullable=False),
    Column("committed", Integer(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

# No entity class - a counter, not a rich domain object. Queried via Core
# directly by SqlRateLimiter.
rate_limit_windows_table = Table(
    "rate_limit_windows",
    metadata,
    Column("id", Uuid(), primary_key=True),
    Column("tenant_id", Uuid(), nullable=False),
    Column("bucket", Text(), nullable=False),
    Column("window_start", DateTime(timezone=True), nullable=False),
    Column("count", Integer(), nullable=False),
)

_mapped = False


def start_mappers() -> None:
    global _mapped
    if _mapped:
        return
    mapper_registry.map_imperatively(User, users_table)
    mapper_registry.map_imperatively(Identity, identities_table)
    mapper_registry.map_imperatively(TenantMembership, tenant_memberships_table)
    mapper_registry.map_imperatively(Session, sessions_table)
    mapper_registry.map_imperatively(Category, categories_table)
    mapper_registry.map_imperatively(AttributeDefinition, attribute_definitions_table)
    mapper_registry.map_imperatively(VariantAxis, variant_axes_table)
    mapper_registry.map_imperatively(VariantAxisValue, variant_axis_values_table)
    mapper_registry.map_imperatively(InputImageSlot, input_image_slots_table)
    mapper_registry.map_imperatively(CatalogImageSlot, catalog_image_slots_table)
    mapper_registry.map_imperatively(
        CatalogSlotInputRequirement, catalog_slot_input_requirements_table
    )
    mapper_registry.map_imperatively(CategorySpecVersion, category_spec_versions_table)
    mapper_registry.map_imperatively(Setting, settings_table)
    mapper_registry.map_imperatively(Asset, assets_table)
    mapper_registry.map_imperatively(CatalogTemplate, catalog_templates_table)
    mapper_registry.map_imperatively(Product, products_table)
    mapper_registry.map_imperatively(ProductVariant, product_variants_table)
    mapper_registry.map_imperatively(ProductInputImage, product_input_images_table)
    mapper_registry.map_imperatively(GenerationRequest, generation_requests_table)
    mapper_registry.map_imperatively(GenerationItem, generation_items_table)
    mapper_registry.map_imperatively(CatalogImage, catalog_images_table)
    _mapped = True
