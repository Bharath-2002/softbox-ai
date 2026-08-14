from __future__ import annotations

import pytest

from app.entities.catalog_template import CatalogTemplate, TemplateKind, TemplateStatus
from app.shared.clock import utcnow
from app.shared.errors import ValidationError
from app.shared.ids import new_asset_id, new_catalog_image_slot_id, new_tenant_id, new_user_id


def _from_upload() -> CatalogTemplate:
    return CatalogTemplate.create_from_upload(
        new_tenant_id(),
        new_catalog_image_slot_id(),
        name="Studio flatlay",
        source_asset_id=new_asset_id(),
        created_by=new_user_id(),
        now=utcnow(),
    )


def test_a_template_created_from_an_upload_starts_uploaded() -> None:
    template = _from_upload()

    assert template.kind == TemplateKind.ANALYSED_IMAGE
    assert template.status == TemplateStatus.UPLOADED
    assert template.source_asset_id is not None
    assert template.prompt_template is None


def test_an_authored_template_has_no_source_asset() -> None:
    template = CatalogTemplate.create_authored(
        new_tenant_id(),
        new_catalog_image_slot_id(),
        name="Marble tabletop",
        prompt_template="A flat-lay on white marble, soft daylight.",
        created_by=new_user_id(),
        now=utcnow(),
    )

    assert template.kind == TemplateKind.AUTHORED_SCENE
    assert template.source_asset_id is None
    assert template.status == TemplateStatus.UPLOADED
    assert template.prompt_template is not None


def test_the_happy_path_reaches_analysed() -> None:
    template = _from_upload()
    now = utcnow()

    template.start_analysing(now=now)
    assert template.status == TemplateStatus.ANALYSING

    template.mark_analysed(
        prompt_template="{{input.bunthi}} on a marble surface",
        analysis={"framing": "flat-lay"},
        analysis_model="test-vision-model",
        now=now,
    )

    assert template.status == TemplateStatus.ANALYSED
    assert template.analysed_at == now
    assert template.prompt_template is not None


def test_analysis_can_fail_and_be_retried() -> None:
    template = _from_upload()
    now = utcnow()
    template.start_analysing(now=now)

    template.mark_analysis_failed(reason="provider timeout", now=now)
    assert template.status == TemplateStatus.ANALYSIS_FAILED
    assert template.analysis_error == "provider timeout"

    template.retry_analysis(now=now)
    assert template.status == TemplateStatus.UPLOADED
    assert template.analysis_error is None


def test_an_unresolvable_placeholder_marks_the_template_invalid() -> None:
    template = _from_upload()
    now = utcnow()
    template.start_analysing(now=now)

    template.mark_invalid(reason="{{input.unknown}} does not resolve", now=now)

    assert template.status == TemplateStatus.INVALID
    assert template.analysis_error is not None


def test_only_an_analysed_template_can_be_archived() -> None:
    template = _from_upload()

    with pytest.raises(ValidationError):
        template.archive(now=utcnow())


def test_analysing_twice_is_rejected() -> None:
    template = _from_upload()
    now = utcnow()
    template.start_analysing(now=now)

    with pytest.raises(ValidationError, match="analysing"):
        template.start_analysing(now=now)


def test_completing_analysis_without_starting_it_is_rejected() -> None:
    template = _from_upload()

    with pytest.raises(ValidationError):
        template.mark_analysed(
            prompt_template="x", analysis=None, analysis_model=None, now=utcnow()
        )


def test_an_archived_template_can_be_archived_again_only_from_analysed() -> None:
    template = _from_upload()
    now = utcnow()
    template.start_analysing(now=now)
    template.mark_analysed(prompt_template="x", analysis=None, analysis_model=None, now=now)

    template.archive(now=now)
    assert template.status == TemplateStatus.ARCHIVED

    with pytest.raises(ValidationError):
        template.archive(now=now)
