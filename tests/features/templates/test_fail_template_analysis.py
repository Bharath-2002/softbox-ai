from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.catalog_template import CatalogTemplate
from app.features.templates.fail_template_analysis import FailTemplateAnalysis
from app.shared.errors import NotFoundError
from app.shared.ids import (
    new_asset_id,
    new_catalog_image_slot_id,
    new_catalog_template_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[FailTemplateAnalysis, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return FailTemplateAnalysis(uow_factory, FakeClock(_NOW)), uow_factory


async def test_failing_analysis_records_the_reason() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    template = CatalogTemplate.create_from_upload(
        tenant_id,
        new_catalog_image_slot_id(),
        name="Studio flatlay",
        source_asset_id=new_asset_id(),
        created_by=new_user_id(),
        now=_NOW,
    )
    template.start_analysing(now=_NOW)
    await uow_factory.catalog_templates.add(template)

    result = await use_case(tenant_id=tenant_id, template_id=template.id, reason="provider timeout")

    assert result.status.value == "analysis_failed"
    assert result.analysis_error == "provider timeout"


async def test_failing_an_unknown_template_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=new_tenant_id(), template_id=new_catalog_template_id(), reason="x")
