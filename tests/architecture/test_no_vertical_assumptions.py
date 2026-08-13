"""The platform must not know what it is selling.

Sarees are the first vertical, not a special case. Every garment-specific concept
belongs in a tenant's category specification — attribute definitions, input image
slots, variant axes — never in code.

This is the single most valuable property of the design and the easiest to lose:
it disappears one convenient `if` at a time, and each one looks reasonable on its
own. So it is checked mechanically rather than left to review.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "app"

# Unambiguously vertical vocabulary. Deliberately excludes generic commerce words
# ("product", "price", "colour") and words with legitimate technical meanings
# ("format", "render") — a rule with false positives gets disabled, and a
# disabled rule protects nothing.
FORBIDDEN_TERMS: tuple[str, ...] = (
    "saree",
    "sari",
    "blouse",
    "pallu",
    "bunthi",
    "zari",
    "lehenga",
    "kurta",
    "dupatta",
    "kanchipuram",
    "banarasi",
)

# Not `\b`: underscore is a word character, so `\bsaree\b` fails to match
# `SAREE_MODE`, `saree_id` or `is_saree` — precisely how this vocabulary appears
# in real code. These lookarounds treat any non-alphanumeric as a boundary, and
# the optional `s` catches plurals.
_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    + "|".join(sorted(FORBIDDEN_TERMS, key=len, reverse=True))
    + r")s?(?![A-Za-z0-9])",
    re.IGNORECASE,
)


def python_sources() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_there_are_sources_to_scan() -> None:
    """Guards against the scan silently passing because it found no files."""
    assert python_sources(), f"no Python sources found under {SRC}"


@pytest.mark.parametrize("path", python_sources(), ids=lambda p: str(p.name))
def test_source_contains_no_vertical_vocabulary(path: Path) -> None:
    offenders: list[str] = []
    for lineno, line in enumerate(path.read_text().splitlines(), start=1):
        match = _PATTERN.search(line)
        if match:
            offenders.append(f"{path}:{lineno}: {match.group(0)!r} in {line.strip()!r}")

    assert not offenders, (
        "vertical-specific vocabulary found in application code. This belongs in a "
        "tenant's category specification, not in code:\n  " + "\n  ".join(offenders)
    )
