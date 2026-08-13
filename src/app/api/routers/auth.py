"""Session-establishing routes: Google SSO login, refresh, logout.

A **fifth** router, deliberately, alongside the four CLAUDE.md §9
documents (``platform``, ``admin``, ``public``, ``webhooks``). Login fits
none of them: ``admin`` requires an already-bound tenant, ``platform``
requires an already-established platform-admin principal, ``public`` is the
shopper-facing storefront read API (and will resolve its tenant from the
Host header once that lands — see ``public.py``), and ``webhooks`` is
inbound provider callbacks authenticated by signature, not a session. There
is no principal at all until one of these routes produces one, so no
existing router's auth posture applies, and no router-level dependency is
attached here — that would be backwards for a route whose entire job is to
create the credential every other router checks.

State/nonce are generated here and handed back to the caller (never stored
server-side — this API is stateless, per D4) to persist and echo back at
``/google/callback``. The caller — a browser-based frontend — is
responsible for surviving the redirect round-trip with them (e.g.
``sessionStorage``); this API's job is to *validate* the round-trip, not to
carry it.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.bootstrap.di import (
    CompleteLoginDep,
    GoogleIdentityProviderDep,
    LogoutDep,
    RefreshSessionDep,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class GoogleLoginResponse(BaseModel):
    authorization_url: str
    state: str
    nonce: str


@router.get("/google/login", response_model=GoogleLoginResponse)
async def google_login(
    redirect_uri: str, provider: GoogleIdentityProviderDep
) -> GoogleLoginResponse:
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    url = await provider.build_authorization_url(
        redirect_uri=redirect_uri, state=state, nonce=nonce
    )
    return GoogleLoginResponse(authorization_url=url, state=state, nonce=nonce)


class GoogleCallbackRequest(BaseModel):
    code: str
    redirect_uri: str
    # The state Google echoed back in the browser redirect, and the state
    # the caller remembers generating before it - two fields, not one,
    # because the comparison must happen server-side to mean anything (a
    # client that only checked this itself before calling us could be
    # bypassed by calling this endpoint directly).
    state: str
    expected_state: str
    nonce: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str


@router.post("/google/callback", response_model=TokenPairResponse)
async def google_callback(
    body: GoogleCallbackRequest, use_case: CompleteLoginDep
) -> TokenPairResponse:
    result = await use_case(
        code=body.code,
        redirect_uri=body.redirect_uri,
        nonce=body.nonce,
        expected_state=body.expected_state,
        received_state=body.state,
    )
    return TokenPairResponse(access_token=result.access_token, refresh_token=result.refresh_token)


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(body: RefreshRequest, use_case: RefreshSessionDep) -> TokenPairResponse:
    result = await use_case(refresh_token=body.refresh_token)
    return TokenPairResponse(access_token=result.access_token, refresh_token=result.refresh_token)


class LogoutRequest(BaseModel):
    refresh_token: str


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: LogoutRequest, use_case: LogoutDep) -> None:
    await use_case(refresh_token=body.refresh_token)
