"""Typed identifiers.

Plain ``UUID`` everywhere would let a ``ProductId`` be passed where a
``TenantId`` is expected and mypy would say nothing. These are ``NewType``s —
zero runtime cost, but ``mypy --strict`` catches the swap at the call site.
"""

from __future__ import annotations

import uuid
from typing import NewType

TenantId = NewType("TenantId", uuid.UUID)
UserId = NewType("UserId", uuid.UUID)


def new_tenant_id() -> TenantId:
    return TenantId(uuid.uuid4())


def new_user_id() -> UserId:
    return UserId(uuid.uuid4())
