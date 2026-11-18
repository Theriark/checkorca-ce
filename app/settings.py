"""Runtime settings, read from the environment (deploy/dokploy.json).

SECRET_KEY, FERNET_KEY and DATABASE_URL are required: without them the process
refuses to start. Error messages name the variable and never include a value.
"""

import base64
import binascii
from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DATABASE_URL_PREFIX = "postgresql+asyncpg://"
MIN_SECRET_KEY_LENGTH = 32

Role = Literal["web", "worker", "all"]
LogLevel = Literal["critical", "error", "warning", "info", "debug"]


class SettingsError(ValueError):
    """The environment does not describe a valid configuration."""


class Settings(BaseSettings):
    """Every setting, one environment variable each (the name in upper case)."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore", frozen=True)

    secret_key: SecretStr
    fernet_key: SecretStr
    # The URL carries the database password, so it is a secret too.
    database_url: SecretStr
    base_url: str = "http://localhost:8080"
    role: Role = "all"
    port: int = Field(default=8080, ge=1, le=65535)
    smtp_port: int = Field(default=2525, ge=1, le=65535)
    log_level: LogLevel = "info"
    # The commit the image was built from (Dockerfile ARG REVISION).
    revision: str = ""

    @field_validator("secret_key")
    @classmethod
    def _secret_key_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(f"must be at least {MIN_SECRET_KEY_LENGTH} characters")
        return value

    @field_validator("fernet_key")
    @classmethod
    def _fernet_key_shape(cls, value: SecretStr) -> SecretStr:
        try:
            raw = base64.urlsafe_b64decode(value.get_secret_value().encode())
        except (binascii.Error, ValueError):
            raw = b""
        if len(raw) != 32:
            raise ValueError("must be a URL-safe base64 encoded 32-byte Fernet key")
        return value

    @field_validator("database_url")
    @classmethod
    def _database_url_driver(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(DATABASE_URL_PREFIX):
            raise ValueError(f"must start with {DATABASE_URL_PREFIX}")
        return value

    @field_validator("base_url")
    @classmethod
    def _base_url_scheme(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("must start with http:// or https://")
        return value.rstrip("/")


def load_settings(**overrides: Any) -> Settings:
    """Build Settings from the environment; keyword overrides win.

    Raises SettingsError that lists every problem by variable name. The
    pydantic error is not chained because its text includes the input values.
    """
    try:
        return Settings(**overrides)
    except ValidationError as error:
        problems = [
            "_".join(str(part) for part in item["loc"]).upper() + ": " + item["msg"]
            for item in error.errors(include_url=False, include_input=False)
        ]
    raise SettingsError("invalid configuration: " + "; ".join(problems))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings; the first call validates the environment."""
    return load_settings()
