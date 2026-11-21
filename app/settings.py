"""Runtime settings, read from the environment (deploy/dokploy.json).

SECRET_KEY, FERNET_KEY and DATABASE_URL are required: without them the process
refuses to start. Error messages name the variable and never include a value.
"""

import base64
import binascii
import os
import re
from functools import lru_cache
from typing import Any, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DATABASE_URL_PREFIX = "postgresql+asyncpg://"
MIN_SECRET_KEY_LENGTH = 32
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
MAIL_DOMAIN_PATTERN = rf"(?:{_LABEL}\.)*{_LABEL}"

Role = Literal["web", "worker", "all"]
LogLevel = Literal["critical", "error", "warning", "info", "debug"]


class SettingsError(ValueError):
    """The environment does not describe a valid configuration."""


def _readable(path: str) -> bool:
    return os.path.isfile(path) and os.access(path, os.R_OK)


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
    # The domain of the inbox addresses (code@MAIL_DOMAIN); empty means the
    # host name of BASE_URL.
    mail_domain: str = Field(default="", max_length=253)
    # STARTTLS on the SMTP listener: the PEM certificate chain and key mounted
    # into the container. Both empty (the default) means no STARTTLS.
    smtp_tls_cert_file: str = ""
    smtp_tls_key_file: str = ""
    log_level: LogLevel = "info"
    # The commit the image was built from (Dockerfile ARG REVISION).
    revision: str = ""
    # Development and Stage seed (app/seed/accounts.py): the admin, then the
    # technician of DEV_SEED_ACCOUNTS, with their passwords.
    dev_seed: bool = False
    dev_seed_accounts: str = ""
    dev_seed_password_admin: SecretStr | None = None
    dev_seed_password_technician: SecretStr | None = None
    # Development and Stage demo data (app/seed/demo.py): 20 fictional clients
    # and 60 jobs with 14 days of history, seeded once by the worker. Same
    # host rule as the seed accounts.
    dev_demo_data: bool = False

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

    @field_validator("mail_domain")
    @classmethod
    def _mail_domain_shape(cls, value: str) -> str:
        value = value.strip().lower()
        if value and not re.fullmatch(MAIL_DOMAIN_PATTERN, value):
            raise ValueError("must be a domain name such as mail.example.com")
        return value

    @model_validator(mode="after")
    def _smtp_tls_pair(self) -> Self:
        if bool(self.smtp_tls_cert_file) != bool(self.smtp_tls_key_file):
            raise ValueError(
                "SMTP_TLS_CERT_FILE and SMTP_TLS_KEY_FILE must be set together"
            )
        # The worker starts the SMTP listener: a missing file would leave port
        # 2525 closed while the process runs, so it refuses to start instead.
        files = (self.smtp_tls_cert_file, self.smtp_tls_key_file)
        worker = self.role != "web"
        if worker and files[0] and not all(map(_readable, files)):
            raise ValueError(
                "SMTP_TLS_CERT_FILE and SMTP_TLS_KEY_FILE must name readable files"
            )
        return self

    @property
    def inbox_domain(self) -> str:
        """The domain of the inbox addresses: MAIL_DOMAIN or BASE_URL's host."""
        return self.mail_domain or (urlsplit(self.base_url).hostname or "localhost")


def known_secrets(settings: Settings) -> list[str]:
    """Every secret value of the settings, for the log redaction (D-6)."""
    values = [
        settings.secret_key.get_secret_value(),
        settings.fernet_key.get_secret_value(),
    ]
    try:
        password = make_url(settings.database_url.get_secret_value()).password
    except (ArgumentError, ValueError):
        password = None
    if password:
        values.append(str(password))
    for secret in (
        settings.dev_seed_password_admin,
        settings.dev_seed_password_technician,
    ):
        if secret is not None and secret.get_secret_value():
            values.append(secret.get_secret_value())
    return values


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
