"""Shared test setup: synthetic settings for every test.

CI provides DATABASE_URL (PostgreSQL 16 service container). The secret values
in helpers.py are synthetic and protect nothing.
"""

import os
from collections.abc import Iterator

import pytest

from app.settings import get_settings
from helpers import TEST_FERNET_KEY, TEST_SECRET_KEY, UNREACHABLE_DATABASE_URL

DATABASE_URL = os.environ.get("DATABASE_URL", UNREACHABLE_DATABASE_URL)


@pytest.fixture(autouse=True)
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """A complete, valid environment; tests remove or change single values."""
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET_KEY)
    monkeypatch.setenv("FERNET_KEY", TEST_FERNET_KEY)
    monkeypatch.setenv("DATABASE_URL", DATABASE_URL)
    for name in ("REVISION", "ROLE", "PORT", "SMTP_PORT", "BASE_URL", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
