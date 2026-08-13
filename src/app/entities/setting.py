"""Hierarchical configuration (D16): one generic table instead of the ~40
bespoke bool/enum columns every SaaS eventually grows for things like
"is approval required" or "which channels does it gate." Resolution is
``platform -> tenant -> category -> product``, most specific wins — see
``services.settings_resolver.SettingsResolver``.

``scope_type`` fixes what ``tenant_id``/``scope_id`` must look like, enforced
both here and by the migration's ``CHECK`` constraint (belt and braces, the
same reasoning every other entity's invariants get):

- ``platform`` — ``tenant_id`` and ``scope_id`` both ``None``. Visible to
  every tenant; writable only by a platform-plane session (no tenant bound).
- ``tenant`` — ``tenant_id`` set, ``scope_id`` ``None``. A tenant-wide
  override.
- ``category`` / ``product`` — both set. ``scope_id`` is a bare id (a
  ``CategoryId``, or a not-yet-existing ``ProductId`` once M4 has one), not
  a foreign key — the same "no FK because the referenced concept doesn't
  own a stable type here" reasoning ``image_slots.example_asset_id`` used
  first.

``key`` is a fixed, platform-defined namespaced string (``approval.required``,
not a tenant-supplied identifier) — unlike D11's ``AttributeDefinition.key``,
it is never turned into a JSONB key, a Pydantic field name, or a Python
identifier anywhere, so it does not go through ``entities.spec_key.validate_key``
(whose dot-rejecting pattern would reject exactly this shape of key).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.shared.errors import ValidationError
from app.shared.ids import SettingId, TenantId, new_setting_id


class SettingScope(StrEnum):
    PLATFORM = "platform"
    TENANT = "tenant"
    CATEGORY = "category"
    PRODUCT = "product"


@dataclass
class Setting:
    id: SettingId
    tenant_id: TenantId | None
    scope_type: SettingScope
    scope_id: uuid.UUID | None
    key: str
    value: Any
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create(
        *,
        scope_type: SettingScope,
        tenant_id: TenantId | None,
        scope_id: uuid.UUID | None,
        key: str,
        value: Any,
        now: datetime,
    ) -> Setting:
        if not key or key.strip() != key:
            raise ValidationError(
                "Setting key must be a non-empty string with no surrounding whitespace."
            )

        if scope_type is SettingScope.PLATFORM:
            if tenant_id is not None or scope_id is not None:
                raise ValidationError("A platform-scoped setting has no tenant or scope id.")
        elif scope_type is SettingScope.TENANT:
            if tenant_id is None or scope_id is not None:
                raise ValidationError("A tenant-scoped setting has a tenant id and no scope id.")
        else:
            if tenant_id is None or scope_id is None:
                raise ValidationError(
                    "A category- or product-scoped setting has both a tenant id and a scope id."
                )

        return Setting(
            id=new_setting_id(),
            tenant_id=tenant_id,
            scope_type=scope_type,
            scope_id=scope_id,
            key=key,
            value=value,
            created_at=now,
            updated_at=now,
        )
