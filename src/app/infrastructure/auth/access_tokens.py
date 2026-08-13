"""Implements ``app.services.ports.token_issuer.TokenIssuer`` with a JWT (D4)
— the stateless half of "short-lived JWT access tokens plus rotating refresh
tokens". The refresh half is ``Session``/``SessionRepository``; this is what
``get_current_principal`` verifies on every request, with no database lookup.

Two details that are easy to get subtly wrong with JWTs, both handled
explicitly rather than left to a library default:

- **The allowed algorithm is pinned at decode time**, not read from the
  token's own header. Trusting the header's ``alg`` is the classic
  algorithm-confusion vulnerability class - a token claiming ``alg: none``,
  or one signed with a different key type than expected, must be rejected
  before its claims are even looked at, not accepted because the header
  said so.
- **``jwt.decode`` verifies the signature but not claims** - expiry and
  issuer are checked separately via ``JWTClaimsRegistry``, explicitly, so
  a token past its ``exp`` cannot slip through.
- **No leeway on expiry, unlike the OIDC id_token path.** Authlib's
  ``parse_id_token`` (used in ``oidc_provider.py``) applies a 120s leeway by
  default - reasonable for tolerating clock skew against a third-party
  issuer. These tokens are issued and verified by us on the same clock, so
  there is no skew to tolerate, and ``JWTClaimsRegistry`` here is left at its
  default ``leeway=0`` deliberately, not by oversight.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from joserfc import jwt
from joserfc.jwk import OctKey
from joserfc.jwt import JWTClaimsRegistry

from app.services.ports.token_issuer import AccessTokenClaims
from app.shared.errors import AuthenticationError

_ALGORITHM = "HS256"
_ISSUER = "softbox-ai"


class AccessTokenCodec:
    def __init__(self, signing_key: str, *, ttl: timedelta = timedelta(minutes=15)) -> None:
        if len(signing_key) < 32:
            # HS256 with a short key is a real weakness, not a style nit -
            # fail at construction, not silently at the first forged token.
            raise ValueError("Access token signing key must be at least 32 characters.")
        self._key = OctKey.import_key(signing_key)
        self._ttl = ttl

    def encode(self, claims: AccessTokenClaims, *, now: datetime) -> str:
        header = {"alg": _ALGORITHM}
        payload: dict[str, Any] = {
            "sub": claims.subject,
            "tenant_id": claims.tenant_id,
            "role": claims.role,
            "capabilities": claims.capabilities,
            "is_platform_admin": claims.is_platform_admin,
            "iss": _ISSUER,
            "iat": int(now.timestamp()),
            "exp": int((now + self._ttl).timestamp()),
        }
        return jwt.encode(header, payload, self._key)

    def decode(self, token: str, *, now: datetime) -> AccessTokenClaims:
        try:
            decoded = jwt.decode(token, self._key, algorithms=[_ALGORITHM])
            registry = JWTClaimsRegistry(
                now=int(now.timestamp()),
                exp={"essential": True},
                iss={"essential": True, "value": _ISSUER},
                sub={"essential": True},
            )
            registry.validate(decoded.claims)
        except Exception as exc:
            raise AuthenticationError("Invalid or expired access token.") from exc

        claims = decoded.claims
        return AccessTokenClaims(
            subject=str(claims["sub"]),
            tenant_id=claims.get("tenant_id"),
            role=claims.get("role"),
            capabilities=list(claims.get("capabilities") or []),
            is_platform_admin=bool(claims.get("is_platform_admin", False)),
        )
