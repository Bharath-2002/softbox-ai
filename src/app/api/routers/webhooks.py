"""Inbound webhooks from external providers.

No blanket router-level dependency: each provider (Instagram, payment, ...)
authenticates a callback its own way — a signature header or shared secret
verified against the raw body — not a bearer token. Each webhook route
carries its own per-provider verification when the first one is built.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
