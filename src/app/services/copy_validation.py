"""D23's brand-rules/forbidden-claims validation pass — enforced as a real
check on the generated copy, not left as prompt instructions a model can
ignore.

Case-insensitive substring matching, deliberately not tokenised: `"silk"`
in a tenant's forbidden list will also flag `"silk-blend"`, and a
concatenated hashtag like `"#purenilk"` (typo aside) matches on substring
inside one token. That is an accepted over-block, not a bug — this pass's
failure mode is "regenerate the copy" (see
`features.content.complete_content_draft_generation`, which fails the
queue job rather than rejecting a product), so a false positive costs a
retry, not a wrongly-published claim. A false negative — a real forbidden
claim slipping through because it was phrased around a substring match —
is the failure this pass exists to avoid, and substring matching is the
conservative direction to err in.
"""

from __future__ import annotations

from app.services.ports.text_generation import GeneratedCopy


def validate_copy(copy: GeneratedCopy, *, forbidden_claims: list[str]) -> str | None:
    """Returns a violation reason, or `None` if the copy is clean."""
    haystack = " ".join(
        [copy.title or "", copy.body, copy.cta or "", " ".join(copy.hashtags)]
    ).lower()
    for claim in forbidden_claims:
        if claim.lower() in haystack:
            return f"Forbidden claim {claim!r} found in generated copy."
    return None
