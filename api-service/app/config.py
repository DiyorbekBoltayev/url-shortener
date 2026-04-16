"""Application settings — pydantic-settings, secrets-aware.

Security notes:
    * ``JWT_SECRET`` MUST be set (>=32 bytes, non-placeholder) for any
      non-development ``ENVIRONMENT``. In development, we auto-generate an
      ephemeral secret on first start and emit a loud warning — tokens minted
      with it will not survive a process restart.
    * ``CORS_ORIGINS`` must never contain ``"*"`` because we send the
      ``allow_credentials=True`` flag in :mod:`app.main`; the combination is
      rejected at runtime by Starlette anyway, but we fail fast at import.
"""
from __future__ import annotations

import os
import secrets
import sys
from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known placeholder values that must never reach a non-development environment.
# Compared case-insensitively against the raw JWT secret.
_JWT_PLACEHOLDERS: frozenset[str] = frozenset({
    "",
    "change_this_to_a_long_random_string",
    "change_this_to_a_long_random_string_at_least_32_bytes",
    "change_this_to_a_long_random_string_at_least_32_chars",
    "dev-change-me-change-me-change-me-change-me",
    "dev-webhook-signing-key",
})
_JWT_MIN_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- Postgres ---------------------------------------------------
    database_url: str = Field(
        default="postgresql+asyncpg://ushortener:changeme_dev_only@postgres:5432/urlshortener",
    )

    # ---- Redis ------------------------------------------------------
    redis_cache_url: str = Field(default="redis://redis-cache:6379/0")
    redis_app_url: str = Field(default="redis://redis-app:6380/0")

    # ---- ClickHouse -------------------------------------------------
    clickhouse_url: str = Field(default="clickhouse://default:@clickhouse:8123/analytics")
    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: SecretStr = SecretStr("")
    clickhouse_db: str = "analytics"

    # ---- JWT --------------------------------------------------------
    # Empty by default; validator below either injects a dev ephemeral
    # or fails fast in non-development environments.
    jwt_secret: SecretStr = SecretStr("")
    jwt_alg: str = "HS256"
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 7

    # ---- CORS -------------------------------------------------------
    cors_origins: list[str] = Field(default_factory=list)

    # ---- Safe Browsing ---------------------------------------------
    safe_browsing_api_key: SecretStr | None = None

    # ---- Safety scan (P0 feature) ----------------------------------
    # ``safety_provider`` picks between the no-op, Google Web Risk, and
    # heuristic backends. Heuristic is the default because it has no
    # runtime deps — keeps dev environments green.
    safety_provider: Literal["none", "google_web_risk", "heuristic"] = "heuristic"
    google_web_risk_api_key: SecretStr | None = None
    safety_denylist_domains: list[str] = Field(default_factory=list)

    # ---- OG / link preview -----------------------------------------
    og_fetch_enabled: bool = True
    og_fetch_timeout_sec: float = 5.0
    og_fetch_max_body_mb: int = 2

    # ---- MinIO / S3 ------------------------------------------------
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: SecretStr = SecretStr("minioadmin")
    minio_secure: bool = False
    minio_bucket_exports: str = "exports"
    minio_bucket_imports: str = "imports"
    minio_bucket_qr_logos: str = "qr-logos"

    # ---- Webhooks ---------------------------------------------------
    webhook_signing_key: SecretStr = SecretStr("dev-webhook-signing-key")

    # ---- Observability ----------------------------------------------
    log_level: str = "INFO"
    environment: str = "development"
    sql_echo: bool = False

    # ---- Rate limits ------------------------------------------------
    rl_default_per_min: int = 120

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("safety_denylist_domains", mode="before")
    @classmethod
    def _split_denylist(cls, v: object) -> object:
        # Comma-separated env var support. Lowercased so matching is
        # case-insensitive across user input.
        if isinstance(v, str):
            return [d.strip().lower() for d in v.split(",") if d.strip()]
        if isinstance(v, list):
            return [str(d).strip().lower() for d in v if str(d).strip()]
        return v

    # -----------------------------------------------------------------
    # Security validators (added FX-SEC / RV10 1.1, 1.2, 1.6)
    # -----------------------------------------------------------------
    @field_validator("cors_origins")
    @classmethod
    def _reject_star_origin(cls, v: list[str]) -> list[str]:
        """Refuse ``"*"`` — we always send ``allow_credentials=True``.

        Starlette's CORS middleware will reject the pair at runtime, but an
        explicit check here surfaces the misconfiguration at process start
        instead of on the first preflight.
        """
        if any(o.strip() == "*" for o in v):
            raise ValueError(
                'CORS_ORIGINS must not contain "*" — the API sends '
                "Access-Control-Allow-Credentials: true, which is "
                "incompatible with a wildcard origin. List exact origins "
                "(e.g. https://app.example.com,https://admin.example.com)."
            )
        return v

    @field_validator("jwt_secret")
    @classmethod
    def _guard_jwt_secret(cls, v: SecretStr) -> SecretStr:
        """Refuse empty/placeholder JWT_SECRET in non-development envs.

        In ``development`` we auto-generate an ephemeral 32-byte secret and
        warn on stderr — useful for first-run DX but never acceptable for
        anything that sees real traffic.

        We read ``ENVIRONMENT`` straight from ``os.environ`` rather than
        :class:`pydantic.ValidationInfo.data` because Pydantic v2 validates
        fields in declaration order — ``environment`` is declared AFTER
        ``jwt_secret`` and therefore is not yet present in ``info.data``
        when this validator fires. Pulling from ``os.environ`` avoids the
        ordering coupling and matches how ``pydantic-settings`` would have
        resolved the env var anyway.
        """
        raw = v.get_secret_value() if v is not None else ""
        env = os.environ.get("ENVIRONMENT", "development").lower()
        is_placeholder = (
            len(raw) < _JWT_MIN_BYTES
            or raw.lower() in _JWT_PLACEHOLDERS
            or "change" in raw.lower()
        )
        if not is_placeholder:
            return v
        if env != "development":
            raise ValueError(
                f"JWT_SECRET must be set to a strong random value of at least "
                f"{_JWT_MIN_BYTES} bytes in ENVIRONMENT={env!r}. Placeholder "
                "or empty values are refused. Generate one with:  "
                "python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        # Development only: mint an ephemeral secret. Log loudly so operators
        # don't ship it by accident; tokens will not survive a restart.
        generated = secrets.token_urlsafe(48)
        print(
            "\n"
            "============================================================\n"
            " WARNING: JWT_SECRET is unset or a placeholder.\n"
            " Auto-generated an EPHEMERAL development secret:\n"
            f"   {generated}\n"
            " All issued tokens will be invalidated on the next restart.\n"
            " Set JWT_SECRET in .env to suppress this warning.\n"
            "============================================================\n",
            file=sys.stderr,
            flush=True,
        )
        return SecretStr(generated)

    @property
    def access_ttl_seconds(self) -> int:
        return self.jwt_access_ttl_min * 60

    @property
    def refresh_ttl_seconds(self) -> int:
        return self.jwt_refresh_ttl_days * 24 * 3600


@lru_cache
def get_settings() -> Settings:
    """Return cached settings (evaluated on first call)."""
    return Settings()


settings = get_settings()
