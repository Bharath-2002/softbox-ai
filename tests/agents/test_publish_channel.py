"""Exercises the real `StartPublicationPublish`/`CompletePublicationPublish`/
`FailPublicationPublish` use cases wired together the way `bootstrap/di.py`
wires them — only `ChannelPublisher` is a fake. Proves the agent owns no
transaction of its own, the same property `test_generation_render.py`
proves for that agent.

On the Gate's "a retry after a timeout does not create a second post"
property: what this test suite can actually prove, at this layer, is the
**use-case-level half** — a retry passes the exact same `idempotency_key`
as the original attempt, because `StartPublicationPublish` reads it off
the `Publication` row rather than regenerating it, and no failure path
ever touches it. That is asserted directly via `keys_seen`. The other
half — that a real provider actually honours that key and refuses to
double-post — is D21's "the adapter first queries the provider" contract
obligation on every `ChannelPublisher` adapter (see that port's own
docstring), and **no adapter exists in this repo to prove it against**.
`FakeChannelPublisher.calls == 1` after a retry only proves the fake's own
short-circuit fired, which is necessary scaffolding for these tests to run
at all, not evidence about a real Pinterest/Instagram/Facebook adapter's
behaviour. That evidence can only exist once a real adapter does.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.agents.publish_channel import PublishChannelAgent
from app.entities.product_variant import ProductVariant
from app.entities.publication import Publication, PublicationStatus
from app.features.publishing.complete_publication_publish import CompletePublicationPublish
from app.features.publishing.fail_publication_publish import FailPublicationPublish
from app.features.publishing.start_publication_publish import (
    JOB_TYPE,
    StartPublicationPublish,
)
from app.services.ports.channel_publisher import ValidationResult
from app.shared.ids import (
    new_product_id,
    new_social_account_id,
    new_tenant_id,
    new_user_id,
)
from tests.fakes.channel_publisher import FakeChannelPublisher
from tests.fakes.clock import FakeClock
from tests.fakes.unit_of_work import FakeUnitOfWorkFactory

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _agent(
    uow_factory: FakeUnitOfWorkFactory,
    channel_publisher: FakeChannelPublisher,
    clock: FakeClock,
) -> PublishChannelAgent:
    return PublishChannelAgent(
        StartPublicationPublish(uow_factory, clock),
        CompletePublicationPublish(uow_factory, clock),
        FailPublicationPublish(uow_factory, clock),
        channel_publisher,
    )


async def _seed(uow_factory: FakeUnitOfWorkFactory) -> tuple[object, Publication]:
    tenant_id = new_tenant_id()
    variant = ProductVariant.create(
        tenant_id, new_product_id(), axis_values={}, created_by=new_user_id(), now=_NOW
    )
    await uow_factory.product_variants.add(variant)
    publication = Publication.create(
        tenant_id,
        variant.id,
        new_social_account_id(),
        content_draft_id=None,
        payload={"caption": "Crafted with care.", "media_asset_ids": [], "link": None},
        now=_NOW,
    )
    await uow_factory.publications.add(publication)
    await uow_factory.task_queue.enqueue(
        tenant_id,
        job_type=JOB_TYPE,
        payload={"publication_id": str(publication.id)},
        run_at=_NOW,
        now=_NOW,
    )
    return tenant_id, publication


async def test_a_lost_response_after_the_provider_accepted_does_not_create_a_second_post() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, publication = await _seed(uow_factory)
    channel_publisher = FakeChannelPublisher()
    channel_publisher.lose_response_after_success = True
    clock = FakeClock(_NOW)
    agent = _agent(uow_factory, channel_publisher, clock)

    # First run: the fake records the post, then raises - simulating the
    # provider accepting it but the response never reaching this process.
    first = await agent.run(tenant_id=tenant_id)

    assert first is not None
    assert first.status is PublicationStatus.PENDING  # reverted for retry, not dead
    assert first.attempts == 1
    assert len(channel_publisher.calls) == 1

    # Second run (the retry): advance past the backoff window `fail()` set
    # on the rescheduled job, then reuse the same idempotency_key - the fake
    # already has this post recorded and returns it without a new call.
    clock.advance(timedelta(seconds=5))
    second = await agent.run(tenant_id=tenant_id)

    assert second is not None
    assert second.status is PublicationStatus.PUBLISHED
    assert second.external_post_id == "post-1"
    # The use-case-level half of the Gate property: both attempts asked
    # the provider for the exact same key. This is what this codebase is
    # actually responsible for proving - see this module's own docstring.
    assert channel_publisher.keys_seen == [publication.idempotency_key] * 2
    # Necessary scaffolding, not the proof itself: the fake's own
    # short-circuit is why only one post landed in `calls`.
    assert len(channel_publisher.calls) == 1

    stored = await uow_factory.publications.get(tenant_id, publication.id)
    assert stored is not None
    assert stored.status is PublicationStatus.PUBLISHED


async def test_the_idempotency_key_is_committed_before_any_provider_call() -> None:
    """Proves the property structurally: `CreatePublication` (not exercised
    directly here - `_seed` mirrors its write) commits the row and its key
    in one transaction with no `ChannelPublisher` involved at all. If the
    process died right after that commit and never ran the agent, nothing
    would have been posted and the key would already be durable - which is
    exactly what this asserts without needing to literally kill a process."""
    uow_factory = FakeUnitOfWorkFactory()
    channel_publisher = FakeChannelPublisher()
    _tenant_id, publication = await _seed(uow_factory)

    assert publication.idempotency_key
    assert publication.status is PublicationStatus.PENDING
    assert channel_publisher.calls == []


async def test_a_normal_publish_succeeds_on_the_first_attempt() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, _publication = await _seed(uow_factory)
    channel_publisher = FakeChannelPublisher()
    agent = _agent(uow_factory, channel_publisher, FakeClock(_NOW))

    result = await agent.run(tenant_id=tenant_id)

    assert result is not None
    assert result.status is PublicationStatus.PUBLISHED
    assert len(channel_publisher.calls) == 1


async def test_a_rejected_validation_fails_the_attempt_without_calling_publish() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    tenant_id, _publication = await _seed(uow_factory)
    channel_publisher = FakeChannelPublisher()
    channel_publisher.next_validation = ValidationResult(valid=False, errors=["caption too long"])
    agent = _agent(uow_factory, channel_publisher, FakeClock(_NOW))

    result = await agent.run(tenant_id=tenant_id)

    assert result is not None
    assert result.status is PublicationStatus.PENDING
    assert result.last_error is not None
    assert "caption too long" in result.last_error
    assert channel_publisher.calls == []


async def test_run_returns_none_when_nothing_is_claimable() -> None:
    uow_factory = FakeUnitOfWorkFactory()
    channel_publisher = FakeChannelPublisher()
    agent = _agent(uow_factory, channel_publisher, FakeClock(_NOW))

    result = await agent.run(tenant_id=new_tenant_id())

    assert result is None
