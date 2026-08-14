from __future__ import annotations

from app.services.copy_prompt_composition import compose_copy_prompt


def test_composes_channel_and_locale_into_the_prompt() -> None:
    prompt = compose_copy_prompt(
        channel="instagram", locale="en", attributes={"colour": "red", "fabric": "silk"}
    )

    assert "instagram" in prompt
    assert "en" in prompt
    assert "colour: red" in prompt
    assert "fabric: silk" in prompt


def test_attributes_are_sorted_for_determinism() -> None:
    prompt_a = compose_copy_prompt(channel="pinterest", locale="en", attributes={"b": 1, "a": 2})
    prompt_b = compose_copy_prompt(channel="pinterest", locale="en", attributes={"a": 2, "b": 1})

    assert prompt_a == prompt_b
