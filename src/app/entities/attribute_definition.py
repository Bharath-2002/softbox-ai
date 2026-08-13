"""A tenant-defined custom field, owned by one category (D11).

Storage is three parts working together (see the migration's docstring for
the storage/validation split): this is the *definition* row only. The value
itself lives in ``products.attributes`` JSONB once products exist (M4) — an
``AttributeDefinition`` never holds product data.

``semantic_role`` is what lets the platform treat a handful of
tenant-defined fields as structurally meaningful (price must sort, title
must go in a caption) without hardcoding what a tenant calls them. Projecting
a role into a real column (``products.price_amount``, ...) is D11's write
path, out of scope until M4 has a ``products`` table to project into.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.shared.ids import AttributeDefinitionId, CategoryId, TenantId, new_attribute_definition_id


class AttributeDataType(StrEnum):
    TEXT = "text"
    LONG_TEXT = "long_text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    MONEY = "money"
    BOOLEAN = "boolean"
    DATE = "date"
    ENUM = "enum"
    MULTI_ENUM = "multi_enum"
    URL = "url"
    IMAGE_REF = "image_ref"
    DIMENSION = "dimension"


class SemanticRole(StrEnum):
    TITLE = "title"
    DESCRIPTION = "description"
    PRICE = "price"
    SKU = "sku"
    BRAND = "brand"
    MATERIAL = "material"
    COLOUR = "colour"


@dataclass
class AttributeDefinition:
    id: AttributeDefinitionId
    tenant_id: TenantId
    category_id: CategoryId
    key: str
    label: str
    help_text: str | None
    data_type: AttributeDataType
    semantic_role: SemanticRole | None
    is_required: bool
    is_filterable: bool
    is_public: bool
    position: int
    validation: dict[str, Any]
    ui: dict[str, Any]
    default_value: Any | None
    introduced_in_version: int | None
    retired_in_version: int | None
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        tenant_id: TenantId,
        category_id: CategoryId,
        *,
        key: str,
        label: str,
        data_type: AttributeDataType,
        now: datetime,
        help_text: str | None = None,
        semantic_role: SemanticRole | None = None,
        is_required: bool = False,
        is_filterable: bool = False,
        is_public: bool = True,
        position: int = 0,
        validation: dict[str, Any] | None = None,
        ui: dict[str, Any] | None = None,
        default_value: Any | None = None,
    ) -> AttributeDefinition:
        return AttributeDefinition(
            id=new_attribute_definition_id(),
            tenant_id=tenant_id,
            category_id=category_id,
            key=key,
            label=label,
            help_text=help_text,
            data_type=data_type,
            semantic_role=semantic_role,
            is_required=is_required,
            is_filterable=is_filterable,
            is_public=is_public,
            position=position,
            validation=validation or {},
            ui=ui or {},
            default_value=default_value,
            introduced_in_version=None,
            retired_in_version=None,
            created_at=now,
            updated_at=now,
        )
