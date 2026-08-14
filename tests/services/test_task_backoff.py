from __future__ import annotations

from datetime import timedelta

from app.services.task_backoff import compute_backoff


def test_zero_jitter_gives_a_zero_delay() -> None:
    assert compute_backoff(1, jitter=0.0) == timedelta(seconds=0)


def test_full_jitter_at_attempt_one_hits_the_base_delay() -> None:
    assert compute_backoff(1, jitter=1.0) == timedelta(seconds=2)


def test_full_jitter_doubles_each_attempt() -> None:
    assert compute_backoff(2, jitter=1.0) == timedelta(seconds=4)
    assert compute_backoff(3, jitter=1.0) == timedelta(seconds=8)


def test_delay_is_capped_for_large_attempt_counts() -> None:
    assert compute_backoff(20, jitter=1.0) == timedelta(seconds=300)


def test_half_jitter_is_half_the_ceiling() -> None:
    assert compute_backoff(1, jitter=0.5) == timedelta(seconds=1)
