"""Builds the prompt `TextGeneration.generate_copy` sends for D23's
per-channel, per-locale marketing copy.

**Known gap, flagged not fixed**: this composes from product/variant
attributes only — it does not ground the copy in the approved imagery
`entities.content_draft`'s own docstring and D23 both describe ("from the
product attributes and the approved imagery"). `TextGeneration.generate_copy`
does not accept reference images today; adding that is a port change, not a
prompt-composition one, and is deliberately not guessed at here. A prompt
parameter that merely encoded an image *count* would launder this gap into
looking handled without actually grounding anything — worse than leaving it
visible.
"""

from __future__ import annotations

from typing import Any

COPY_PROMPT_VERSION = "v1"


def compose_copy_prompt(*, channel: str, locale: str, attributes: dict[str, Any]) -> str:
    attribute_lines = "\n".join(f"- {key}: {value}" for key, value in sorted(attributes.items()))
    return (
        f"Write marketing copy for the {channel} channel, in locale {locale}.\n"
        "Product attributes:\n"
        f"{attribute_lines}\n\n"
        "Return a title, body, hashtags, a call to action, and image alt text, "
        "matching the voice conventional for this channel."
    )
