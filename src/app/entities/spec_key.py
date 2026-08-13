"""The identifier-safety rule shared by every taxonomy "definition" entity's
``key`` field (D10-D13): ``AttributeDefinition``, ``VariantAxis``, and
(commit 4b) the input/catalog image slot pools.

A ``key`` is used as a ``products.attributes``/``axis_values`` JSONB key, a
runtime Pydantic field name (``attribute_model_compiler.py``), and a D14
prompt placeholder segment (``{{attr.fabric}}``, ``{{variant.colour}}``).
One shared check, not a copy per entity that could quietly drift out of
sync with the others and reopen exactly the gap this exists to close.
"""

from __future__ import annotations

import re

from app.shared.errors import ValidationError

_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_key(key: str, *, what: str = "Key") -> None:
    if not _KEY_PATTERN.match(key):
        raise ValidationError(
            f"{what} {key!r} must be lowercase, start with a letter, and contain only "
            "letters, digits and underscores.",
            code="invalid_key",
        )
