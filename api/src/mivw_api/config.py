"""Layered application configuration.

Resolution order: defaults -> config file -> environment -> CLI.
Key *material* is never read from configuration; only key identifiers are, and
the actual keys are resolved at runtime from a KMS or the OS keychain.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, PostgresDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Mode(StrEnum):
    LOCAL = "local"
    SERVER = "server"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MIVW_",
        env_file=(".env", ".env.local"),
        env_nested_delimiter="__",
        extra="forbid",
    )

    mode: Mode = Mode.LOCAL
    log_level: str = "INFO"

    # --- database ---------------------------------------------------------
    db_dsn: PostgresDsn
    db_pool_min: int = Field(default=2, ge=1)
    db_pool_max: int = Field(default=16, ge=1)

    # --- object store -----------------------------------------------------
    object_endpoint: str = "http://localhost:9000"
    object_bucket: str = "mivw-volumes"
    object_region: str = "us-east-1"
    presigned_url_ttl_seconds: int = Field(default=300, le=900)

    # --- identity ---------------------------------------------------------
    oidc_issuer: str
    oidc_audience: str
    oidc_jwks_ttl_seconds: int = 3600
    jwt_leeway_seconds: int = Field(default=5, le=30)

    # --- cryptography (identifiers only, never key material) --------------
    encryption_key_id: str
    hmac_key_id: str

    # --- rendering --------------------------------------------------------
    gpu_device: int = 0
    render_session_idle_timeout_s: int = 900
    render_max_sessions_per_user: int = Field(default=4, ge=1, le=16)
    render_still_delay_ms: int = 150

    # --- inference --------------------------------------------------------
    trt_engine_cache_dir: Path = Path(".cache/trt")
    trt_engine_cache_max_gb: int = 20

    # --- server mode only -------------------------------------------------
    tls_cert_file: Path | None = None
    tls_key_file: Path | None = None
    mtls_ca_file: Path | None = None
    allowed_origin: str | None = None

    @field_validator("log_level")
    @classmethod
    def _valid_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {sorted(allowed)}")
        return upper

    @model_validator(mode="after")
    def _server_mode_requires_tls(self) -> Settings:
        """Server mode carries PHI over a network, so TLS is not optional."""
        if self.mode is Mode.SERVER:
            missing = [
                name
                for name, value in (
                    ("tls_cert_file", self.tls_cert_file),
                    ("tls_key_file", self.tls_key_file),
                    ("mtls_ca_file", self.mtls_ca_file),
                    ("allowed_origin", self.allowed_origin),
                )
                if value is None
            ]
            if missing:
                raise ValueError(f"MIVW_MODE=server requires: {', '.join(sorted(missing))}")
        return self

    @property
    def bind_host(self) -> str:
        # Local mode must never be reachable off-box.
        return "127.0.0.1" if self.mode is Mode.LOCAL else "0.0.0.0"  # noqa: S104  # nosec B104

    @property
    def cors_origins(self) -> list[str]:
        return [self.allowed_origin] if self.allowed_origin else []


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
