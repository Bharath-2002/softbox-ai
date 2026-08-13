"""Runtime Pydantic model compilation from ``AttributeDefinition`` rows (D11).

One compiled class drives both API validation (``model_validate``) and
admin-UI form rendering (``model_json_schema``) — they cannot drift, because
there is only one model, not a hand-maintained pair.

Pydantic here is a validation library, not a web framework — the same
distinction ``api/routers`` already draws by using it for request/response
schemas. This module has no FastAPI import and no HTTP concern; it belongs
in ``services`` because it depends only on entities and is a pure function
of them, the same as ``spec_inheritance``.

Field name is the definition's ``key`` — safe by construction, since
``AttributeDefinition.create`` rejects anything that is not a valid
lowercase identifier (see that entity's module docstring for why).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model

from app.entities.attribute_definition import AttributeDataType, AttributeDefinition
from app.shared.ids import CategoryId

_PYTHON_TYPE: dict[AttributeDataType, type] = {
    AttributeDataType.TEXT: str,
    AttributeDataType.LONG_TEXT: str,
    AttributeDataType.INTEGER: int,
    AttributeDataType.DECIMAL: Decimal,
    AttributeDataType.MONEY: int,  # minor units (CLAUDE.md §12) - never a float
    AttributeDataType.BOOLEAN: bool,
    AttributeDataType.DATE: date,
    AttributeDataType.ENUM: str,
    AttributeDataType.MULTI_ENUM: list[str],
    AttributeDataType.URL: str,
    AttributeDataType.IMAGE_REF: str,  # an asset id/reference; Asset itself is M3
    AttributeDataType.DIMENSION: dict[str, float],
}


def _field_type(definition: AttributeDefinition) -> Any:
    options = definition.validation.get("options")
    if definition.data_type is AttributeDataType.ENUM and options:
        return Literal[tuple(options)]
    if definition.data_type is AttributeDataType.MULTI_ENUM and options:
        # mypy cannot verify a `Literal[...]` built from a runtime tuple -
        # this whole function's return is `Any` regardless; the check exists
        # for pydantic's benefit at model-validation time, not mypy's.
        return list[Literal[tuple(options)]]  # type: ignore[misc]
    return _PYTHON_TYPE[definition.data_type]


def _field_constraints(definition: AttributeDefinition) -> dict[str, Any]:
    v = definition.validation
    constraints: dict[str, Any] = {}
    if "min" in v:
        constraints["ge"] = v["min"]
    if "max" in v:
        constraints["le"] = v["max"]
    if "maxLength" in v:
        constraints["max_length"] = v["maxLength"]
    if "regex" in v:
        constraints["pattern"] = v["regex"]
    return constraints


def compile_attribute_model(
    model_name: str, definitions: list[AttributeDefinition]
) -> type[BaseModel]:
    """Pure — no caching here (see ``AttributeModelCache`` for that).
    ``definitions`` should already be the resolved, inheritance-aware view
    (``spec_inheritance.resolve_inherited``), not raw per-category rows."""
    fields: dict[str, Any] = {}
    for definition in definitions:
        field_type = _field_type(definition)
        default = ... if definition.is_required else definition.default_value
        if not definition.is_required:
            field_type = field_type | None
        fields[definition.key] = (
            field_type,
            Field(default, title=definition.label, **_field_constraints(definition)),
        )
    return create_model(model_name, **fields)


class AttributeModelCache:
    """Caches a compiled model by ``(category_id, spec_version)`` (D11).

    The cache trusts its key: it does not re-check whether ``definitions``
    changed since the last call for the same key. That is by design — a
    published ``category_spec_version`` is immutable (D15), so the same
    ``spec_version`` for a given category always implies the same
    definitions. Callers still mid-draft (no spec version minted yet) should
    not use this cache at all; compile directly instead.
    """

    def __init__(self) -> None:
        self._models: dict[tuple[CategoryId, int], type[BaseModel]] = {}

    def get_or_compile(
        self, category_id: CategoryId, spec_version: int, definitions: list[AttributeDefinition]
    ) -> type[BaseModel]:
        key = (category_id, spec_version)
        cached = self._models.get(key)
        if cached is not None:
            return cached
        model = compile_attribute_model(
            f"AttributeModel_{category_id.hex}_{spec_version}", definitions
        )
        self._models[key] = model
        return model
