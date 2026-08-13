from __future__ import annotations

from app.entities.category_spec_version import CategorySpecVersion, SpecVersionStatus
from app.shared.clock import utcnow
from app.shared.ids import new_category_id, new_tenant_id, new_user_id


def test_create_always_produces_a_published_row() -> None:
    version = CategorySpecVersion.create(
        new_tenant_id(),
        new_category_id(),
        version=1,
        snapshot={"attribute_definitions": []},
        published_by=new_user_id(),
        now=utcnow(),
    )

    assert version.status is SpecVersionStatus.PUBLISHED


def test_create_carries_the_snapshot_and_optional_change_summary() -> None:
    snapshot = {"attribute_definitions": [{"key": "fabric"}]}
    change_summary = {"added": ["fabric"]}

    version = CategorySpecVersion.create(
        new_tenant_id(),
        new_category_id(),
        version=2,
        snapshot=snapshot,
        published_by=new_user_id(),
        now=utcnow(),
        change_summary=change_summary,
    )

    assert version.snapshot == snapshot
    assert version.change_summary == change_summary


def test_change_summary_defaults_to_none() -> None:
    version = CategorySpecVersion.create(
        new_tenant_id(),
        new_category_id(),
        version=1,
        snapshot={},
        published_by=new_user_id(),
        now=utcnow(),
    )

    assert version.change_summary is None
