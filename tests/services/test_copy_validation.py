from __future__ import annotations

from app.services.copy_validation import validate_copy
from app.services.ports.text_generation import GeneratedCopy


def _copy(**overrides: object) -> GeneratedCopy:
    defaults: dict[str, object] = {
        "title": "A handwoven classic",
        "body": "Crafted with care.",
        "hashtags": ["#saree"],
        "cta": "Shop now",
        "alt_text": "A folded saree.",
        "model": "fake-text-model",
        "cost_micros": 0,
        "latency_ms": 0,
    }
    defaults.update(overrides)
    return GeneratedCopy(**defaults)  # type: ignore[arg-type]


def test_clean_copy_has_no_violation() -> None:
    assert validate_copy(_copy(), forbidden_claims=["cures arthritis"]) is None


def test_no_forbidden_claims_configured_never_violates() -> None:
    assert validate_copy(_copy(body="cures arthritis instantly"), forbidden_claims=[]) is None


def test_a_forbidden_claim_in_the_body_is_caught() -> None:
    violation = validate_copy(
        _copy(body="This saree cures arthritis."), forbidden_claims=["cures arthritis"]
    )

    assert violation is not None
    assert "cures arthritis" in violation


def test_matching_is_case_insensitive() -> None:
    violation = validate_copy(
        _copy(body="This saree CURES ARTHRITIS."), forbidden_claims=["cures arthritis"]
    )

    assert violation is not None


def test_a_forbidden_claim_spanning_hashtags_is_caught() -> None:
    violation = validate_copy(
        _copy(hashtags=["#cures", "arthritis"]), forbidden_claims=["cures arthritis"]
    )

    assert violation is not None
