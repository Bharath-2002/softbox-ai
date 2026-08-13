"""Operator plane: platform admins only (D4).

Structurally separate from the ``admin`` router rather than a capability
check within it — a platform admin's authority does not come from, and is
not limited by, any tenant's role assignments (``Principal`` docstring).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps.authorization import require_platform_admin

router = APIRouter(
    prefix="/platform", tags=["platform"], dependencies=[Depends(require_platform_admin)]
)
