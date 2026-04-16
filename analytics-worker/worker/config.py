"""Pydantic-settings configuration.

Env-var names align with INTEGRATION_CONTRACT.md section 4 (analytics-worker).
All overrideable via .env or process environment.
"""
from __future__ import annotations

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Redis (app db, stream source) ---
    redis_stream_url: str = "redis://redis-app:6380/0"

    # --- ClickHouse (sink) ---
    clickhouse_host: str = "clickhouse"
    clickhouse_port: int = 9000
    clickhouse_http_port: int = 8123
    clickhouse_db: str = "analytics"
    clickhouse_user: str = "default"
    clickhouse_password: SecretStr = SecretStr("")

    # --- Stream contract (LOCKED) ---
    stream_name: str = "stream:clicks"
    consumer_group: str = "analytics"

    # --- Batching ---
    batch_size: int = Field(1000, ge=1, le=50_000)
    flush_interval_sec: float = Field(1.0, ge=0.05, le=30.0)
    read_count: int = Field(100, ge=1, le=10_000)
    read_block_ms: int = Field(5_000, ge=100, le=60_000)

    # --- PEL reclaimer ---
    pel_idle_ms: int = Field(300_000, ge=1_000)
    pel_claim_interval_sec: float = Field(60.0, ge=1.0)
    pel_max_deliveries: int = Field(16, ge=1)

    # --- GeoIP ---
    geoip_db_path: str = "/data/GeoLite2-City.mmdb"

    # --- Observability ---
    metrics_port: int = 9091
    health_port: int = 9092
    log_level: str = "INFO"


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
