"""Application configuration.

Settings live in the composition root. Adapters do **not** import this module —
``bootstrap`` reads configuration and passes concrete values into the adapters it
constructs. That keeps every adapter independently constructible in a test
without an environment.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOFTBOX_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    environment: Environment = "local"
    debug: bool = False

    # ── Logging ──────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # Console rendering is for humans at a terminal; anything shipped to a log
    # aggregator must be JSON.
    log_format: Literal["json", "console"] = "json"

    # ── Database ─────────────────────────────────────────────────────────────
    # SecretStr so an accidental repr() or model_dump() cannot spill the password.
    database_url: SecretStr = Field(
        default=SecretStr("postgresql+asyncpg://softbox_app@localhost:5432/softbox"),
    )
    database_pool_size: int = 10
    database_max_overflow: int = 5
    database_echo: bool = False

    # ── HTTP ─────────────────────────────────────────────────────────────────
    api_prefix: str = "/api/v1"
    cors_origins: tuple[str, ...] = ()

    # ── Auth (D4) ────────────────────────────────────────────────────────────
    # HS256 signing key for our own access tokens (app.infrastructure.auth.
    # access_tokens) - never the OIDC provider's credentials, which are
    # per-provider config not yet added (no route constructs an
    # IdentityProvider yet; that lands with the /auth/* routers).
    access_token_signing_key: SecretStr = Field(
        default=SecretStr("dev-only-access-token-signing-key-not-for-production-use"),
    )

    # Google's discovery document is a fixed, well-known URL, not a secret -
    # kept overridable (a non-Google IdP in a future test, a different
    # Google Cloud project) rather than hardcoded in the adapter.
    google_client_id: str = ""
    google_client_secret: SecretStr = Field(default=SecretStr(""))
    google_discovery_url: str = "https://accounts.google.com/.well-known/openid-configuration"

    # Users whose email lands here are granted platform_admin on login if
    # they do not already have it (CompleteLogin's bootstrap_admin_emails) -
    # an explicit, operator-configured allowlist, not domain inference,
    # consistent with D4's "explicit grant, never inferred". This solves an
    # otherwise-real chicken-and-egg problem: nothing in the system can grant
    # the first platform admin without one already existing to do the
    # granting.
    admin_emails: tuple[str, ...] = ()

    # ── Email ────────────────────────────────────────────────────────────────
    # "console" (log instead of sending) is the default - local dev and CI
    # have no real SMTP credentials, and .env.example's SMTP_PASSWORD is a
    # placeholder, not one.
    email_backend: Literal["smtp", "console"] = "console"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: SecretStr = Field(default=SecretStr(""))
    email_from: str = "Softbox AI <no-reply@example.com>"

    # ── Object storage (D17) ────────────────────────────────────────────────
    # "local" (filesystem, this process serving its own presigned URLs) is
    # the only backend today - no S3/R2 bucket or credentials are configured
    # anywhere in this repo (see CHECKLIST.md's M3 STATE entry). Real object
    # storage is a "stop and ask" per CLAUDE.md - a new external dependency -
    # flagged there rather than guessed at here.
    object_storage_backend: Literal["local"] = "local"
    object_storage_local_root: str = "./.data/object-storage"
    object_storage_public_base_url: str = "http://localhost:8000"
    object_storage_signing_key: SecretStr = Field(
        default=SecretStr("dev-only-object-storage-signing-key-not-for-production-use"),
    )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings.

    Cached because reading and validating the environment on every request is
    waste. Tests that need different settings construct ``Settings(...)``
    directly rather than clearing this cache.
    """
    return Settings()
