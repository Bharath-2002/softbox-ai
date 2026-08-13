"""Opaque bearer secrets — refresh tokens, and anything else that is a random
value compared by its hash, never its plaintext, once issued.

Plaintext exists only once, at the moment of issuance, in the response
handed to the caller. It is never stored — only its hash is (D3, D22's
credential-handling discipline applied to something we issue rather than
something a tenant hands us).
"""

from __future__ import annotations

import hashlib
import secrets


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
