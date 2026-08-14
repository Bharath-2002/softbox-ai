"""Validates a `ProductVariant.axis_values` map against a category's pinned
spec snapshot (D12, D15) — reads `snapshot["variant_axes"]`, the same pinned
blob `product_readiness` reads for input slots, never the LIVE
`variant_axes`/`variant_axis_values` tables. Pure, same shape as
`template_placeholder_validator`: returns problem strings rather than
raising, so a caller can decide what to do with them.

An axis with no declared values (``values`` empty) accepts any string — not
every axis is necessarily an enumerated set yet. An axis key not present in
the snapshot at all is always a problem.
"""

from __future__ import annotations

from typing import Any


def validate_axis_values(snapshot: dict[str, Any], axis_values: dict[str, str]) -> list[str]:
    axes_by_key = {axis["key"]: axis for axis in snapshot.get("variant_axes", [])}
    problems: list[str] = []
    for key, value in axis_values.items():
        axis = axes_by_key.get(key)
        if axis is None:
            problems.append(f"Unknown variant axis {key!r}.")
            continue
        allowed = {v["value"] for v in axis["values"]}
        if allowed and value not in allowed:
            problems.append(
                f"{value!r} is not a valid value for axis {key!r} "
                f"(allowed: {', '.join(sorted(allowed))})."
            )
    return problems
