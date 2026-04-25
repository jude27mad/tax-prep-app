from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, cast

from pydantic import BaseModel, Field
from pydantic import ConfigDict, field_validator, model_validator

ENV_BOOL_TRUE = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in ENV_BOOL_TRUE


def _env_env() -> Literal["CERT", "PROD"]:
    upper = os.getenv("EFILE_ENV", "CERT").upper()
    normalized = upper if upper in {"CERT", "PROD"} else "CERT"
    return cast(Literal["CERT", "PROD"], normalized)


@dataclass(frozen=True)
class EfileProfile:
    environment: Literal["CERT", "PROD"]
    software_id: str
    software_version: str
    transmitter_id: str
    endpoint: str | None


class Settings(BaseModel):
    feature_efile_xml: bool = Field(default_factory=lambda: _env_bool("FEATURE_EFILE_XML", False))
    feature_legacy_efile: bool = Field(
        default_factory=lambda: _env_bool("FEATURE_LEGACY_EFILE", False)
    )
    feature_2025_transmit: bool = Field(
        default_factory=lambda: _env_bool("FEATURE_2025_TRANSMIT", False)
    )
    efile_environment: Literal["CERT", "PROD"] = Field(default_factory=_env_env)
    software_id_cert: str = Field(default_factory=lambda: os.getenv("EFILE_SOFTWARE_ID_CERT", "TAXAPP-CERT"))
    software_id_prod: str = Field(default_factory=lambda: os.getenv("EFILE_SOFTWARE_ID_PROD", "TAXAPP-PROD"))
    transmitter_id_cert: str = Field(default_factory=lambda: os.getenv("EFILE_TRANSMITTER_ID_CERT", "900000"))
    transmitter_id_prod: str = Field(default_factory=lambda: os.getenv("EFILE_TRANSMITTER_ID_PROD", "900001"))
    software_version: str = Field(default_factory=lambda: os.getenv("SOFTWARE_VERSION", "0.0.3"))
    endpoint_cert: str | None = Field(default_factory=lambda: os.getenv("EFILE_ENDPOINT_CERT", "http://127.0.0.1:9000"))
    endpoint_prod: str | None = Field(default_factory=lambda: os.getenv("EFILE_ENDPOINT_PROD", "https://prod-placeholder"))
    build_version: str = Field(default_factory=lambda: os.getenv("BUILD_VERSION", "dev"))
    build_sha: str = Field(default_factory=lambda: os.getenv("BUILD_SHA", "local"))
    artifact_root: str = Field(default_factory=lambda: os.getenv("ARTIFACT_ROOT", "artifacts"))
    daily_summary_root: str = Field(default_factory=lambda: os.getenv("DAILY_SUMMARY_ROOT", "artifacts/summaries"))
    schema_version_manifest: str | None = Field(default_factory=lambda: os.getenv("SCHEMA_VERSION_MANIFEST"))
    t183_crypto_key: str | None = Field(default_factory=lambda: os.getenv("T183_CRYPTO_KEY"))
    transmit_max_retries: int = Field(default_factory=lambda: int(os.getenv("TRANSMIT_MAX_RETRIES", "3")))
    transmit_backoff_factor: float = Field(default_factory=lambda: float(os.getenv("TRANSMIT_BACKOFF", "0.5")))
    transmit_circuit_threshold: int = Field(default_factory=lambda: int(os.getenv("TRANSMIT_CIRCUIT_THRESHOLD", "5")))
    transmit_circuit_cooldown: float = Field(default_factory=lambda: float(os.getenv("TRANSMIT_CIRCUIT_COOLDOWN", "30")))
    efile_window_open: bool = Field(default_factory=lambda: _env_bool("EFILE_WINDOW_OPEN", False))
    retention_t2183_enabled: bool = Field(default_factory=lambda: _env_bool("RETENTION_T2183_ENABLED", False))
    # D1.3 — persistent document vault.
    # When DATABASE_URL is set it wins; otherwise we build a SQLite path from db_path.
    database_url: str | None = Field(default_factory=lambda: os.getenv("DATABASE_URL"))
    db_path: str = Field(default_factory=lambda: os.getenv("DB_PATH", "tax_app.db"))

    # D1.4 — magic-link auth. session_secret is MANDATORY in prod; the
    # dev default is documented and refuses to sign anything in CERT/PROD
    # unless overridden. auth_email_backend picks the transport (console
    # only for Phase 1; smtp/provider adapters land later).
    session_secret: str = Field(
        default_factory=lambda: os.getenv(
            "AUTH_SESSION_SECRET",
            "dev-only-change-me-do-not-use-in-prod",
        )
    )
    auth_email_backend: str = Field(
        default_factory=lambda: os.getenv("AUTH_EMAIL_BACKEND", "console")
    )
    auth_token_ttl_minutes: int = Field(
        default_factory=lambda: int(os.getenv("AUTH_TOKEN_TTL_MINUTES", "15"))
    )

    # D1.7 — SMTP transport for magic links. Required only when
    # auth_email_backend="smtp"; otherwise these are inert. We validate the
    # required pair (host + from) in a model_validator so misconfigured
    # prod boots fail loudly instead of silently dropping login emails.
    auth_smtp_host: str | None = Field(
        default_factory=lambda: os.getenv("AUTH_SMTP_HOST")
    )
    auth_smtp_port: int = Field(
        default_factory=lambda: int(os.getenv("AUTH_SMTP_PORT", "587"))
    )
    auth_smtp_username: str | None = Field(
        default_factory=lambda: os.getenv("AUTH_SMTP_USERNAME")
    )
    auth_smtp_password: str | None = Field(
        default_factory=lambda: os.getenv("AUTH_SMTP_PASSWORD")
    )
    auth_smtp_use_tls: bool = Field(
        default_factory=lambda: _env_bool("AUTH_SMTP_USE_TLS", True)
    )
    auth_smtp_use_ssl: bool = Field(
        default_factory=lambda: _env_bool("AUTH_SMTP_USE_SSL", False)
    )
    auth_smtp_timeout: float = Field(
        default_factory=lambda: float(os.getenv("AUTH_SMTP_TIMEOUT", "10"))
    )
    auth_smtp_from: str | None = Field(
        default_factory=lambda: os.getenv("AUTH_SMTP_FROM")
    )
    auth_smtp_subject: str = Field(
        default_factory=lambda: os.getenv(
            "AUTH_SMTP_SUBJECT", "Your sign-in link"
        )
    )

    # D1.7 — rate limit on POST /auth/request. Per-email caps the obvious
    # abuse of mailbombing one address; per-IP caps drive-by enumeration
    # from a single source. Both windows share the same duration (seconds).
    # The limiter is in-memory: behind a multi-worker deploy the effective
    # cap multiplies by worker count. Future work moves this to Redis if
    # we add horizontal scaling.
    auth_request_rate_per_email: int = Field(
        default_factory=lambda: int(os.getenv("AUTH_REQUEST_RATE_PER_EMAIL", "5"))
    )
    auth_request_rate_per_ip: int = Field(
        default_factory=lambda: int(os.getenv("AUTH_REQUEST_RATE_PER_IP", "10"))
    )
    auth_request_rate_window_seconds: int = Field(
        default_factory=lambda: int(
            os.getenv("AUTH_REQUEST_RATE_WINDOW_SECONDS", "900")
        )
    )

    model_config = ConfigDict(frozen=True)

    @field_validator("efile_environment", mode="before")
    @classmethod
    def _normalize_env(cls, value: str) -> str:
        upper = (value or "CERT").upper()
        if upper not in {"CERT", "PROD"}:
            raise ValueError(f"EFILE_ENV must be CERT or PROD, got {upper}")
        return upper

    @field_validator("transmit_max_retries")
    @classmethod
    def _validate_retries(cls, value: int) -> int:
        return max(1, value)

    @field_validator("transmit_backoff_factor")
    @classmethod
    def _validate_backoff(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("TRANSMIT_BACKOFF must be positive")
        return value

    @field_validator("transmit_circuit_threshold")
    @classmethod
    def _validate_threshold(cls, value: int) -> int:
        return max(1, value)

    @field_validator("auth_token_ttl_minutes")
    @classmethod
    def _validate_token_ttl(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("AUTH_TOKEN_TTL_MINUTES must be positive")
        return value

    @field_validator("auth_smtp_port")
    @classmethod
    def _validate_smtp_port(cls, value: int) -> int:
        if not (1 <= value <= 65535):
            raise ValueError("AUTH_SMTP_PORT must be between 1 and 65535")
        return value

    @field_validator("auth_smtp_timeout")
    @classmethod
    def _validate_smtp_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("AUTH_SMTP_TIMEOUT must be positive")
        return value

    @field_validator(
        "auth_request_rate_per_email",
        "auth_request_rate_per_ip",
        "auth_request_rate_window_seconds",
    )
    @classmethod
    def _validate_rate_limit(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Rate-limit settings must be positive integers")
        return value

    @model_validator(mode="after")
    def _require_endpoints(self) -> "Settings":
        profile = self.profile()
        if profile.endpoint is None:
            raise ValueError(f"Missing EFILE endpoint for environment {profile.environment}")
        return self

    @model_validator(mode="after")
    def _require_smtp_when_selected(self) -> "Settings":
        # Validating here (instead of at lifespan time) so misconfigured
        # prod boots fail before SessionMiddleware accepts any traffic.
        # Tests / dev that don't opt into SMTP keep the zero-config path.
        if self.auth_email_backend == "smtp":
            missing = [
                name
                for name, value in (
                    ("AUTH_SMTP_HOST", self.auth_smtp_host),
                    ("AUTH_SMTP_FROM", self.auth_smtp_from),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"AUTH_EMAIL_BACKEND=smtp requires {', '.join(missing)}."
                )
            if self.auth_smtp_use_tls and self.auth_smtp_use_ssl:
                raise ValueError(
                    "AUTH_SMTP_USE_TLS and AUTH_SMTP_USE_SSL are mutually exclusive."
                )
        return self

    def profile(self) -> EfileProfile:
        env = self.efile_environment
        if env not in {"CERT", "PROD"}:
            env = "CERT"
        if env == "CERT":
            return EfileProfile(
                environment="CERT",
                software_id=self.software_id_cert,
                software_version=self.software_version,
                transmitter_id=self.transmitter_id_cert,
                endpoint=self.endpoint_cert,
            )
        return EfileProfile(
            environment="PROD",
            software_id=self.software_id_prod,
            software_version=self.software_version,
            transmitter_id=self.transmitter_id_prod,
            endpoint=self.endpoint_prod,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
