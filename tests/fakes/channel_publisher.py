"""Three explicit, settable failure modes — written before any use case
that consumes this port, per the design this port's own docstring
requires: a fake shaped to prove the Gate property, not shaped to pass
whatever test gets written against it later.

- Normal: `publish()` records the post and returns.
- Lost response: `lose_response_after_success = True` records the post
  (exactly as a provider that actually accepted it would have) and *then*
  raises, simulating "the provider took it, but we never saw the
  response." One-shot — cleared after firing once.
- Rejected: `next_publish_error` raises before anything is recorded, so a
  retry (same key or a fresh one) is a clean first attempt.

`calls` counts only the attempts that actually reached the fake provider
and were recorded — a retry that returns the already-stored result via
the same `idempotency_key` does **not** append here.

`keys_seen` appends on *every* `publish()` entry, before the short-circuit
— unlike `calls`, it records what each attempt asked for, not what each
attempt did. This is what a caller-level test should actually assert
against: that a retry passes the *same* key as the original attempt is a
property of `StartPublicationPublish`/`Publication` (they read the row's
key rather than regenerating it), not of this fake. `calls == 1` after a
retry only proves this fake's own internal short-circuit fired — see
`tests/agents/test_publish_channel.py`'s docstring for why that is a
weaker claim than it looks.
"""

from __future__ import annotations

from app.services.ports.channel_publisher import (
    ChannelCapabilities,
    ChannelMetrics,
    PublishPayload,
    PublishResult,
    ValidationResult,
)

_DEFAULT_CAPABILITIES = ChannelCapabilities(
    max_media=10, max_caption_length=2200, supports_video=True
)


class FakeChannelPublisher:
    def __init__(self, *, capabilities: ChannelCapabilities | None = None) -> None:
        self.capabilities = capabilities or _DEFAULT_CAPABILITIES
        self.calls: list[PublishPayload] = []
        self.keys_seen: list[str] = []
        self.next_validation: ValidationResult | None = None
        self.next_publish_error: Exception | None = None
        self.lose_response_after_success = False
        self._posts_by_key: dict[str, PublishResult] = {}
        self._next_sequence = 0

    async def validate(self, payload: PublishPayload) -> ValidationResult:
        if self.next_validation is not None:
            return self.next_validation
        return ValidationResult(valid=True, errors=[])

    async def publish(self, payload: PublishPayload, *, idempotency_key: str) -> PublishResult:
        self.keys_seen.append(idempotency_key)
        existing = self._posts_by_key.get(idempotency_key)
        if existing is not None:
            return existing

        if self.next_publish_error is not None:
            error = self.next_publish_error
            self.next_publish_error = None
            raise error

        self.calls.append(payload)
        self._next_sequence += 1
        result = PublishResult(
            external_post_id=f"post-{self._next_sequence}",
            permalink=f"https://example.test/p/{self._next_sequence}",
        )
        # Recorded before the "lost response" branch below - a real
        # provider that accepted the post did so regardless of whether its
        # own response reaches this caller.
        self._posts_by_key[idempotency_key] = result

        if self.lose_response_after_success:
            self.lose_response_after_success = False
            raise TimeoutError("simulated: the provider accepted the post, the response was lost")

        return result

    async def fetch_metrics(self, external_id: str) -> ChannelMetrics:
        return ChannelMetrics(impressions=0, likes=0, clicks=0)
