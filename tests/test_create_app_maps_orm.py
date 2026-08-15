"""Regression test for a real bug: ``create_app()`` never called
``start_mappers()`` (mapping.py's own docstring: "must run exactly once,
before any query against an entity"). Every other test in this suite was
blind to it — ``tests/conftest.py`` maps the ORM once, session-scoped,
before any test runs at all, including every router test that builds its
own app via ``create_app()``. That ordering means the bug was invisible
from inside this test process no matter what a normal test called.

A fresh subprocess is the only way to actually prove it: it imports
``create_app`` with nothing else having mapped anything first, exactly the
situation a real deployment starts in.
"""

from __future__ import annotations

import subprocess
import sys


def test_create_app_maps_the_orm_with_no_prior_setup() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.bootstrap.app import create_app\n"
            "from app.bootstrap.settings import Settings\n"
            "create_app(Settings(environment='test', log_format='console'))\n"
            "from app.infrastructure.persistence.mapping import mapper_registry\n"
            "assert mapper_registry.mappers, 'nothing was mapped'\n"
            "print('ok')\n",
        ],
        capture_output=True,
        text=True,
        cwd="src",
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"
