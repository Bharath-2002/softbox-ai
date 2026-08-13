"""Behaviour of ``SqlUnitOfWork`` that does not require a live database.

The tenant-scoping and RLS-visibility behaviour this class exists for is
Postgres-specific (``set_config``, row-level security) and is proven against a
real database in ``test_tenant_isolation.py`` instead — a fake here would only
prove the fake was written consistently with itself.
"""

from __future__ import annotations

import pytest

from app.infrastructure.persistence.unit_of_work import SqlUnitOfWork, make_unit_of_work_factory
from app.shared.ids import new_tenant_id


def test_session_is_inaccessible_before_entering() -> None:
    uow = SqlUnitOfWork(session_factory=object(), tenant_id=None)  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="outside its"):
        _ = uow.session


def test_factory_binds_the_tenant_it_was_given() -> None:
    tenant_id = new_tenant_id()
    factory = make_unit_of_work_factory(session_factory=object())  # type: ignore[arg-type]

    uow = factory(tenant_id)

    assert isinstance(uow, SqlUnitOfWork)
    assert uow._tenant_id == tenant_id


def test_factory_defaults_to_no_tenant() -> None:
    factory = make_unit_of_work_factory(session_factory=object())  # type: ignore[arg-type]

    uow = factory()

    assert uow._tenant_id is None
