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
