"""Named capabilities (D4): permissions are checked as capabilities, never as
role names directly. A role is just a convenient bundle of these.

Deliberately a small, named set rather than an exhaustive taxonomy invented
ahead of the features that need it — a new capability gets added here in the
same commit as the feature that checks it, not speculatively now. See
``roles.ROLE_CAPABILITIES`` for which roles hold which.
"""

from __future__ import annotations

from enum import StrEnum


class Capability(StrEnum):
    CATALOG_PUBLISH = "catalog.publish"
    CATALOG_APPROVE = "catalog.approve"
    PRODUCT_MANAGE = "product.manage"
    TEMPLATE_MANAGE = "template.manage"
    MEMBER_MANAGE = "member.manage"
    SETTINGS_MANAGE = "settings.manage"
