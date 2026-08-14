"""Composes the final prompt string for one generation attempt — "scene +
input refs + attrs + variant" (`docs/DIAGRAMS.md`'s Generation flow, G5).

The scene half substitutes `{{attr.<key>}}` and `{{variant.<key>}}`
placeholders in the template's `prompt_template` with the resolved
product/variant values. `{{input.<key>}}` placeholders are left untouched
in the scene text — they name attached reference images, not text —
`render_role_lines` (this module's sibling) produces the text block
describing those images separately, appended after the scene.

D14a already validated every placeholder in `prompt_template` resolves
against the pinned spec snapshot before a template reaches `analysed`
(`template_placeholder_validator`) — this module reuses its exact
`{{namespace.key}}` regex (`PLACEHOLDER_PATTERN`/`PLACEHOLDER_SHAPE_PATTERN`)
rather than re-deriving it, so the two modules can never silently drift
into recognising different placeholder shapes. A `{{attr.*}}`/
`{{variant.*}}` key missing from the *product's actual data* (not the spec)
is still possible even after that validation passes — the spec says the
key exists, not that every product filled it in — and is a real, actionable
failure (`ValidationError`), not something to paper over with an empty
string.

`attributes` must already be the **merged** view (`merge_attributes`
below) — `ProductVariant.attributes` is a sparse override of
`Product.attributes` (`entities.product_variant`'s own docstring), and
composing a prompt from the unmerged product dict would silently ignore a
variant's override.

Deliberately does **not** implement D12's recolour hex-injection ("no
photographed variant input -> inject colour + hex as a recolour
instruction") — that decision needs to know whether this variant has its
own photographed inputs, which is I/O this pure function has no way to do.
`{{variant.colour}}` substitutes to the plain axis value (e.g. `"maroon"`)
today; the recolour special case is left as an open item on the fan-out
step, which already has to fetch `product_input_images` for other reasons.

`COMPOSITION_VERSION` is `generation_items.prompt_version`'s value — a
version identifier for *this module's own rendering logic*, distinct from
`CatalogTemplate.prompt_version` (an `int`, the template row's own version,
never bumped after creation today). `docs/DIAGRAMS.md`'s ERD deliberately
types `generation_items.prompt_version` as `text`, not `int`, for exactly
this reason — confirmed against the ERD rather than assumed. Bump this
string whenever this module's rendering behaviour changes materially, so an
old attempt's row stays distinguishable from a new one independent of
which template produced it.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.prompt_rendering import render_role_lines
from app.services.template_placeholder_validator import (
    PLACEHOLDER_PATTERN,
    PLACEHOLDER_SHAPE_PATTERN,
)
from app.shared.errors import ValidationError

COMPOSITION_VERSION = "composition-v1"


def merge_attributes(
    product_attributes: dict[str, Any], variant_attributes: dict[str, Any]
) -> dict[str, Any]:
    """The variant's sparse override wins over the product's own value."""
    return {**product_attributes, **variant_attributes}


def compose_prompt(
    snapshot: dict[str, Any],
    *,
    catalog_image_slot_id: str,
    prompt_template: str,
    attributes: dict[str, Any],
    axis_values: dict[str, str],
) -> str:
    scene = _substitute_scene(prompt_template, attributes=attributes, axis_values=axis_values)
    role_lines = render_role_lines(snapshot, catalog_image_slot_id=catalog_image_slot_id)
    if not role_lines:
        return scene
    return f"{scene}\n\n" + "\n".join(role_lines)


def _substitute_scene(
    prompt_template: str, *, attributes: dict[str, Any], axis_values: dict[str, str]
) -> str:
    def _replace(match: re.Match[str]) -> str:
        shape = PLACEHOLDER_SHAPE_PATTERN.match(match.group(1))
        if shape is None:
            return match.group(0)
        namespace, key = shape.group(1), shape.group(2)
        if namespace == "attr":
            if key not in attributes:
                raise ValidationError(f"Product has no value for attribute {key!r}.")
            return str(attributes[key])
        if namespace == "variant":
            if key not in axis_values:
                raise ValidationError(f"Variant has no value for axis {key!r}.")
            return str(axis_values[key])
        # "input" placeholders (and anything malformed) are left untouched —
        # they name reference images, not substitutable text.
        return match.group(0)

    return PLACEHOLDER_PATTERN.sub(_replace, prompt_template)
