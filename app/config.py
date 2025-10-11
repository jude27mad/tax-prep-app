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

    @model_validator(mode="after")
    def _require_endpoints(self) -> "Settings":
        profile = self.profile()
        if profile.endpoint is None:
            raise ValueError(f"Missing EFILE endpoint for environment {profile.environment}")
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
