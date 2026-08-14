"""Templates (D14): analysed once, versioned, prompt placeholders validated
at analysis time (D14a). Two authoring paths (D0's resolution) share one
state machine:

- ``analysed_image`` — ``source_asset_id`` points at an uploaded reference
  photo; a vision model produces ``analysis``/``prompt_template``, an
  asynchronous step that starts in ``uploaded`` and moves to ``analysing``.
- ``authored_scene`` — a human writes ``prompt_template`` directly (the
  stock scene preset library is entirely this kind); there is no photo to
  analyse, but placeholder validation (D14a) still applies, so this path
  runs through the same states with no externally-observable ``analysing``
  wait.

```
uploaded ──▶ analysing ──▶ analysed ──▶ archived
                │              │
                ├──▶ analysis_failed (retryable, ─▶ uploaded)
                └──▶ invalid  (placeholder validation failed — D14a)
```

Only an ``analysed`` template is selectable for generation. Templates are
immutable once analysed — editing produces a new version (a new row); this
entity enforces the state machine but not versioning, which is a
repository/use-case concern (finding the current max version for a
``(tenant_id, catalog_image_slot_id, name)`` group).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.shared.errors import ValidationError
from app.shared.ids import (
    AssetId,
    CatalogImageSlotId,
    CatalogTemplateId,
    TenantId,
    UserId,
    new_catalog_template_id,
)


class TemplateKind(StrEnum):
    ANALYSED_IMAGE = "analysed_image"
    AUTHORED_SCENE = "authored_scene"


class TemplateStatus(StrEnum):
    UPLOADED = "uploaded"
    ANALYSING = "analysing"
    ANALYSED = "analysed"
    ANALYSIS_FAILED = "analysis_failed"
    INVALID = "invalid"
    ARCHIVED = "archived"


@dataclass
class CatalogTemplate:
    id: CatalogTemplateId
    tenant_id: TenantId
    catalog_image_slot_id: CatalogImageSlotId
    name: str
    version: int
    is_default: bool
    position: int
    kind: TemplateKind
    source_asset_id: AssetId | None
    status: TemplateStatus
    analysis: dict[str, Any] | None
    prompt_template: str | None
    prompt_version: int | None
    analysis_model: str | None
    analysed_at: datetime | None
    analysis_error: str | None
    created_by: UserId
    created_at: datetime
    updated_at: datetime

    @staticmethod
    def create_from_upload(
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        *,
        name: str,
        source_asset_id: AssetId,
        created_by: UserId,
        now: datetime,
        version: int = 1,
        is_default: bool = False,
        position: int = 0,
    ) -> CatalogTemplate:
        return CatalogTemplate(
            id=new_catalog_template_id(),
            tenant_id=tenant_id,
            catalog_image_slot_id=catalog_image_slot_id,
            name=name,
            version=version,
            is_default=is_default,
            position=position,
            kind=TemplateKind.ANALYSED_IMAGE,
            source_asset_id=source_asset_id,
            status=TemplateStatus.UPLOADED,
            analysis=None,
            prompt_template=None,
            prompt_version=None,
            analysis_model=None,
            analysed_at=None,
            analysis_error=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def create_authored(
        tenant_id: TenantId,
        catalog_image_slot_id: CatalogImageSlotId,
        *,
        name: str,
        prompt_template: str,
        created_by: UserId,
        now: datetime,
        version: int = 1,
        is_default: bool = False,
        position: int = 0,
    ) -> CatalogTemplate:
        return CatalogTemplate(
            id=new_catalog_template_id(),
            tenant_id=tenant_id,
            catalog_image_slot_id=catalog_image_slot_id,
            name=name,
            version=version,
            is_default=is_default,
            position=position,
            kind=TemplateKind.AUTHORED_SCENE,
            source_asset_id=None,
            status=TemplateStatus.UPLOADED,
            analysis=None,
            prompt_template=prompt_template,
            prompt_version=1,
            analysis_model=None,
            analysed_at=None,
            analysis_error=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )

    def start_analysing(self, *, now: datetime) -> None:
        if self.status != TemplateStatus.UPLOADED:
            raise ValidationError(f"Cannot start analysis from status {self.status.value!r}.")
        self.status = TemplateStatus.ANALYSING
        self.updated_at = now

    def mark_analysed(
        self,
        *,
        prompt_template: str,
        analysis: dict[str, Any] | None,
        analysis_model: str | None,
        now: datetime,
    ) -> None:
        if self.status != TemplateStatus.ANALYSING:
            raise ValidationError(f"Cannot complete analysis from status {self.status.value!r}.")
        self.status = TemplateStatus.ANALYSED
        self.prompt_template = prompt_template
        self.analysis = analysis
        self.analysis_model = analysis_model
        self.analysed_at = now
        self.analysis_error = None
        self.updated_at = now

    def mark_invalid(self, *, reason: str, now: datetime) -> None:
        if self.status != TemplateStatus.ANALYSING:
            raise ValidationError(
                f"Cannot invalidate a template from status {self.status.value!r}."
            )
        self.status = TemplateStatus.INVALID
        self.analysis_error = reason
        self.updated_at = now

    def mark_analysis_failed(self, *, reason: str, now: datetime) -> None:
        if self.status != TemplateStatus.ANALYSING:
            raise ValidationError(f"Cannot fail analysis from status {self.status.value!r}.")
        self.status = TemplateStatus.ANALYSIS_FAILED
        self.analysis_error = reason
        self.updated_at = now

    def retry_analysis(self, *, now: datetime) -> None:
        if self.status != TemplateStatus.ANALYSIS_FAILED:
            raise ValidationError(f"Cannot retry analysis from status {self.status.value!r}.")
        self.status = TemplateStatus.UPLOADED
        self.analysis_error = None
        self.updated_at = now

    def archive(self, *, now: datetime) -> None:
        if self.status != TemplateStatus.ANALYSED:
            raise ValidationError("Only an analysed template can be archived.")
        self.status = TemplateStatus.ARCHIVED
        self.updated_at = now
