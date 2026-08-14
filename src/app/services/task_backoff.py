"""Bounded-retry backoff for the task queue (D19: "exponential backoff with
jitter, then a dead state"). "Full jitter" (AWS's well-known algorithm,
not this codebase's invention): the delay is a random draw between 0 and
``min(cap, base * 2**(attempt-1))``, rather than the delay itself plus a
small perturbation — spreading retries across the whole window is what
actually prevents a thundering herd when many jobs fail at once, which a
narrow +/-10% jitter does not.

``jitter`` is an injected ``float`` in ``[0, 1)`` rather than this module
calling ``random.random()`` itself, so the function stays pure and its own
test is deterministic — the one call site that needs real randomness
(``TaskQueue.fail``) supplies it.

``STUCK_JOB_THRESHOLD`` lives here rather than next to ``TaskQueue.reap_stuck``
because it is the same kind of timing policy as the backoff constants, not a
query concern. ARCHITECTURE.md documents this queue's jobs as "dominated by
30-second external image calls" — 10 minutes is a wide margin above any
legitimate single provider call (including read-reference-images plus the
call itself), so a job still ``running`` past it means the worker that
claimed it crashed or was killed, not that it is slow.
"""

from __future__ import annotations

from datetime import timedelta

_BASE_SECONDS = 2.0
_CAP_SECONDS = 300.0

STUCK_JOB_THRESHOLD = timedelta(minutes=10)


def compute_backoff(attempt: int, *, jitter: float) -> timedelta:
    """``attempt`` is the 1-indexed count of the attempt that just failed."""
    ceiling = min(_CAP_SECONDS, _BASE_SECONDS * (2 ** (attempt - 1)))
    return timedelta(seconds=ceiling * jitter)
