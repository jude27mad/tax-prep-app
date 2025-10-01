from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic import ConfigDict

ENV_BOOL_TRUE = {"1", "true", "yes", "on"}


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in ENV_BOOL_TRUE


@dataclass(frozen=True)
class EfileProfile:
    environment: Literal["CERT", "PROD"]
    software_id: str
    software_version: str
    transmitter_id: str
    endpoint: str | None


class Settings(BaseModel):
    feature_efile_xml: bool = Field(default_factory=lambda: _env_bool("FEATURE_EFILE_XML", False))
    efile_environment: Literal["CERT", "PROD"] = Field(default_factory=lambda: os.getenv("EFILE_ENV", "CERT").upper())
    software_id_cert: str = Field(default_factory=lambda: os.getenv("EFILE_SOFTWARE_ID_CERT", "TAXAPP-CERT"))
    software_id_prod: str = Field(default_factory=lambda: os.getenv("EFILE_SOFTWARE_ID_PROD", "TAXAPP-PROD"))
    transmitter_id_cert: str = Field(default_factory=lambda: os.getenv("EFILE_TRANSMITTER_ID_CERT", "900000"))
    transmitter_id_prod: str = Field(default_factory=lambda: os.getenv("EFILE_TRANSMITTER_ID_PROD", "900001"))
    software_version: str = Field(default_factory=lambda: os.getenv("SOFTWARE_VERSION", "0.0.3"))
    endpoint_cert: str | None = Field(default_factory=lambda: os.getenv("EFILE_ENDPOINT_CERT"))
    endpoint_prod: str | None = Field(default_factory=lambda: os.getenv("EFILE_ENDPOINT_PROD"))
    build_version: str = Field(default_factory=lambda: os.getenv("BUILD_VERSION", "dev"))
    build_sha: str = Field(default_factory=lambda: os.getenv("BUILD_SHA", "local"))

    model_config = ConfigDict(frozen=True)

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
