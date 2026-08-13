"""Tenant membership roles (D4).

Capability *resolution* — turning a role plus a membership's
``extra_capabilities`` into an allow/deny decision for a specific action —
lives with ``Principal`` in the identity feature, not here. This module only
names the roles a membership can hold.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    CATALOG_MANAGER = "catalog_manager"
    APPROVER = "approver"
    VIEWER = "viewer"
