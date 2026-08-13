"""Process-wide test setup.

``start_mappers()`` must run exactly once, before any query against an
ORM-mapped entity (``User``, ``Identity``, ``TenantMembership``, ``Session``)
anywhere in the suite - autouse so no individual test module has to remember
to call it, and session-scoped because SQLAlchemy does not support re-mapping
a class.
"""

from __future__ import annotations

import pytest

from app.infrastructure.persistence.mapping import start_mappers


@pytest.fixture(autouse=True, scope="session")
def _mapped_entities() -> None:
    start_mappers()
