from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.entities.catalog_template import CatalogTemplate
from app.features.templates.archive_template import ArchiveTemplate
from app.shared.errors import NotFoundError, ValidationError
from app.shared.ids import (
    new_catalog_image_slot_id,
    new_catalog_template_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _use_case() -> tuple[ArchiveTemplate, FakeUnitOfWorkFactory]:
    uow_factory = FakeUnitOfWorkFactory()
    return ArchiveTemplate(uow_factory, FakeClock(_NOW)), uow_factory


async def test_archiving_an_analysed_template_succeeds() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    template = CatalogTemplate.create_authored(
        tenant_id,
        new_catalog_image_slot_id(),
        name="x",
        prompt_template="x",
        created_by=new_user_id(),
        now=_NOW,
    )
    template.start_analysing(now=_NOW)
    template.mark_analysed(prompt_template="x", analysis=None, analysis_model=None, now=_NOW)
    await uow_factory.catalog_templates.add(template)

    result = await use_case(tenant_id=tenant_id, template_id=template.id)

    assert result.status.value == "archived"


async def test_archiving_a_template_that_is_not_analysed_is_rejected() -> None:
    use_case, uow_factory = _use_case()
    tenant_id = new_tenant_id()
    template = CatalogTemplate.create_authored(
        tenant_id,
        new_catalog_image_slot_id(),
        name="x",
        prompt_template="x",
        created_by=new_user_id(),
        now=_NOW,
    )
    await uow_factory.catalog_templates.add(template)

    with pytest.raises(ValidationError):
        await use_case(tenant_id=tenant_id, template_id=template.id)


async def test_archiving_an_unknown_template_is_not_found() -> None:
    use_case, _uow_factory = _use_case()

    with pytest.raises(NotFoundError):
        await use_case(tenant_id=new_tenant_id(), template_id=new_catalog_template_id())
