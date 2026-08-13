"""Typed identifiers.

Plain ``UUID`` everywhere would let a ``ProductId`` be passed where a
``TenantId`` is expected and mypy would say nothing. These are ``NewType``s —
zero runtime cost, but ``mypy --strict`` catches the swap at the call site.
"""

from __future__ import annotations

import uuid
from typing import NewType

TenantId = NewType("TenantId", uuid.UUID)
UserId = NewType("UserId", uuid.UUID)
IdentityId = NewType("IdentityId", uuid.UUID)
TenantMembershipId = NewType("TenantMembershipId", uuid.UUID)
SessionId = NewType("SessionId", uuid.UUID)
CategoryId = NewType("CategoryId", uuid.UUID)
AttributeDefinitionId = NewType("AttributeDefinitionId", uuid.UUID)
VariantAxisId = NewType("VariantAxisId", uuid.UUID)
VariantAxisValueId = NewType("VariantAxisValueId", uuid.UUID)
InputImageSlotId = NewType("InputImageSlotId", uuid.UUID)
CatalogImageSlotId = NewType("CatalogImageSlotId", uuid.UUID)


def new_tenant_id() -> TenantId:
    return TenantId(uuid.uuid4())


def new_user_id() -> UserId:
    return UserId(uuid.uuid4())


def new_identity_id() -> IdentityId:
    return IdentityId(uuid.uuid4())


def new_tenant_membership_id() -> TenantMembershipId:
    return TenantMembershipId(uuid.uuid4())


def new_session_id() -> SessionId:
    return SessionId(uuid.uuid4())


def new_category_id() -> CategoryId:
    return CategoryId(uuid.uuid4())


def new_attribute_definition_id() -> AttributeDefinitionId:
    return AttributeDefinitionId(uuid.uuid4())


def new_variant_axis_id() -> VariantAxisId:
    return VariantAxisId(uuid.uuid4())


def new_variant_axis_value_id() -> VariantAxisValueId:
    return VariantAxisValueId(uuid.uuid4())


def new_input_image_slot_id() -> InputImageSlotId:
    return InputImageSlotId(uuid.uuid4())


def new_catalog_image_slot_id() -> CatalogImageSlotId:
    return CatalogImageSlotId(uuid.uuid4())
