from __future__ import annotations

from datetime import UTC, datetime

from app.entities.catalog_template import CatalogTemplate
from app.entities.generation_item import GenerationItem
from app.services.qc_retry_ladder import next_rung
from app.shared.ids import (
    new_catalog_image_slot_id,
    new_catalog_template_id,
    new_generation_request_id,
    new_tenant_id,
    new_user_id,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _item(*, attempt_no: int, template_id: object) -> GenerationItem:
    return GenerationItem.create(
        new_tenant_id(),
        new_generation_request_id(),
        new_catalog_image_slot_id(),
        template_id,  # type: ignore[arg-type]
        attempt_no=attempt_no,
        provider="nano-banana",
        model="nano-banana-2",
        model_params={},
        seed=1,
        prompt_rendered="a scene",
        prompt_version="composition-v1",
        input_asset_ids=[],
        now=_NOW,
    )


def _template(*, slot_id: object, is_default: bool = False) -> CatalogTemplate:
    return CatalogTemplate.create_authored(
        new_tenant_id(),
        slot_id,  # type: ignore[arg-type]
        name=f"template-{new_user_id()}",
        prompt_template="a scene",
        created_by=new_user_id(),
        now=_NOW,
        is_default=is_default,
    )


def test_first_failure_retries_with_the_same_template_and_a_new_seed() -> None:
    template_id = new_catalog_template_id()
    attempts = [_item(attempt_no=1, template_id=template_id)]

    rung = next_rung(attempts, alternate_templates=[])

    assert rung is not None
    assert rung.attempt_no == 2
    assert rung.template_id == template_id
    assert rung.reuse_prompt is True


def test_second_failure_retries_with_a_different_analysed_template() -> None:
    slot_id = new_catalog_image_slot_id()
    failed_template_id = new_catalog_template_id()
    attempts = [
        _item(attempt_no=1, template_id=failed_template_id),
        _item(attempt_no=2, template_id=failed_template_id),
    ]
    alternate = _template(slot_id=slot_id)
    alternate.start_analysing(now=_NOW)
    alternate.mark_analysed(prompt_template="a scene", analysis=None, analysis_model=None, now=_NOW)

    rung = next_rung(attempts, alternate_templates=[alternate])

    assert rung is not None
    assert rung.attempt_no == 3
    assert rung.template_id == alternate.id
    assert rung.reuse_prompt is False


def test_second_failure_with_no_alternate_analysed_template_is_exhausted() -> None:
    template_id = new_catalog_template_id()
    attempts = [
        _item(attempt_no=1, template_id=template_id),
        _item(attempt_no=2, template_id=template_id),
    ]

    assert next_rung(attempts, alternate_templates=[]) is None


def test_second_failure_ignores_an_unanalysed_alternate_template() -> None:
    slot_id = new_catalog_image_slot_id()
    template_id = new_catalog_template_id()
    attempts = [
        _item(attempt_no=1, template_id=template_id),
        _item(attempt_no=2, template_id=template_id),
    ]
    unanalysed = _template(slot_id=slot_id)

    assert next_rung(attempts, alternate_templates=[unanalysed]) is None


def test_third_failure_is_exhausted() -> None:
    template_id = new_catalog_template_id()
    attempts = [
        _item(attempt_no=1, template_id=template_id),
        _item(attempt_no=2, template_id=template_id),
        _item(attempt_no=3, template_id=template_id),
    ]

    assert next_rung(attempts, alternate_templates=[]) is None
