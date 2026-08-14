"""Tenant-admin plane: authenticated and acting within a bound tenant.

The dependency is attached at the router level, not per endpoint — a route
mounted here inherits ``require_tenant_context`` by construction and cannot
be added without it. Individual endpoints still add their own
``require_capability(...)`` where an action needs more than "any tenant
member".
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps.authorization import require_tenant_context
from app.api.routers import (
    admin_assets,
    admin_attributes,
    admin_catalog_images,
    admin_content,
    admin_generation,
    admin_image_slots,
    admin_products,
    admin_publishing,
    admin_settings,
    admin_taxonomy,
    admin_templates,
)

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_tenant_context)])
router.include_router(admin_taxonomy.router)
router.include_router(admin_attributes.router)
router.include_router(admin_image_slots.router)
router.include_router(admin_settings.router)
router.include_router(admin_assets.router)
router.include_router(admin_templates.router)
router.include_router(admin_products.router)
router.include_router(admin_generation.router)
router.include_router(admin_catalog_images.router)
router.include_router(admin_content.router)
router.include_router(admin_publishing.router)
