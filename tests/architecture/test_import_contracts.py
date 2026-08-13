"""The architecture contracts must hold — and must be capable of failing.

A contract that has never been seen to fail is frequently a misconfigured one:
`lint-imports` reports success just as happily when `root_package` is wrong, when
a layer name is misspelled, or when the package is not importable. So this module
asserts both directions — the real tree passes, and a deliberate violation is
caught.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


# The console script, not `python -m importlinter.cli` — the latter exits 0
# without running anything, which would make every assertion here vacuous.
LINT_IMPORTS = Path(sys.executable).parent / "lint-imports"


def run_lint_imports() -> subprocess.CompletedProcess[str]:
    assert LINT_IMPORTS.is_file(), f"lint-imports not found at {LINT_IMPORTS}"
    return subprocess.run(
        [str(LINT_IMPORTS)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


@contextmanager
def violating_module(path: Path, source: str) -> Iterator[None]:
    """Write a module that breaks a contract, then remove it unconditionally."""
    path.write_text(source)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def test_contracts_pass_on_the_real_tree() -> None:
    result = run_lint_imports()
    assert result.returncode == 0, (
        f"import contracts are violated:\n{result.stdout}\n{result.stderr}"
    )


@pytest.mark.parametrize(
    ("contract", "module_path", "source"),
    [
        pytest.param(
            "layers",
            SRC / "app" / "entities" / "_violation.py",
            "from app import features  # noqa: F401\n",
            id="entities-may-not-import-features",
        ),
        pytest.param(
            "infra_isolation",
            SRC / "app" / "features" / "_violation.py",
            "from app import infrastructure  # noqa: F401\n",
            id="features-may-not-import-infrastructure",
        ),
        pytest.param(
            "pure_domain",
            SRC / "app" / "entities" / "_violation.py",
            "import sqlalchemy  # noqa: F401\n",
            id="entities-may-not-import-sqlalchemy",
        ),
        pytest.param(
            "services_no_web",
            SRC / "app" / "services" / "_violation.py",
            "import fastapi  # noqa: F401\n",
            id="services-may-not-import-fastapi",
        ),
        pytest.param(
            "infra_does_not_import_bootstrap",
            SRC / "app" / "infrastructure" / "_violation.py",
            "from app import bootstrap  # noqa: F401\n",
            id="infrastructure-may-not-import-bootstrap",
        ),
    ],
)
def test_contract_catches_a_deliberate_violation(
    contract: str, module_path: Path, source: str
) -> None:
    with violating_module(module_path, source):
        result = run_lint_imports()

    assert result.returncode != 0, (
        f"the {contract!r} contract did not flag a deliberate violation — "
        f"it is not actually enforcing anything.\n{result.stdout}"
    )
    assert contract in result.stdout.lower().replace(" ", "_") or "broken" in result.stdout.lower()
