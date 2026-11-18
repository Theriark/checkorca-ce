"""Settings: required variables, validation, and no values in errors."""

import pytest

from app.settings import Settings, SettingsError, get_settings, load_settings


def test_missing_secret_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(SettingsError, match="SECRET_KEY"):
        load_settings()


def test_every_missing_required_variable_is_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("SECRET_KEY", "FERNET_KEY", "DATABASE_URL"):
        monkeypatch.delenv(name)
    with pytest.raises(SettingsError) as caught:
        load_settings()
    message = str(caught.value)
    for name in ("SECRET_KEY", "FERNET_KEY", "DATABASE_URL"):
        assert name in message


def test_short_secret_key_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "too-short")
    with pytest.raises(SettingsError, match="SECRET_KEY: .*at least 32"):
        load_settings()


@pytest.mark.parametrize("value", ["not-base64!", "c2hvcnQ="])
def test_invalid_fernet_key_fails(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("FERNET_KEY", value)
    with pytest.raises(SettingsError, match="FERNET_KEY"):
        load_settings()


def test_database_url_must_use_asyncpg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://checkorca@db.test/checkorca")
    with pytest.raises(SettingsError, match="DATABASE_URL: .*postgresql\\+asyncpg"):
        load_settings()


@pytest.mark.parametrize(("name", "value"), [("ROLE", "everything"), ("PORT", "0")])
def test_invalid_optional_values_fail(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(SettingsError, match=name):
        load_settings()


def test_base_url_needs_a_web_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASE_URL", "ce-dev-checkorca.theriark.dev")
    with pytest.raises(SettingsError, match="BASE_URL"):
        load_settings()


def test_errors_never_contain_the_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "canary-secret")
    monkeypatch.setenv("FERNET_KEY", "canary-fernet")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:canary-password@db.test/x")
    with pytest.raises(SettingsError) as caught:
        load_settings()
    assert "canary" not in str(caught.value)
    assert caught.value.__cause__ is None
    assert caught.value.__context__ is None


def test_valid_environment_and_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BASE_URL", "https://ce-dev-checkorca.theriark.dev/")
    settings = load_settings()
    assert settings.port == 8080
    assert settings.smtp_port == 2525
    assert settings.role == "all"
    assert settings.log_level == "info"
    assert settings.revision == ""
    assert settings.base_url == "https://ce-dev-checkorca.theriark.dev"
    assert settings.database_url.get_secret_value().startswith("postgresql+asyncpg")


def test_secrets_are_hidden_in_repr() -> None:
    settings = load_settings()
    text = repr(settings) + str(settings)
    assert settings.secret_key.get_secret_value() not in text
    assert settings.fernet_key.get_secret_value() not in text
    assert settings.database_url.get_secret_value() not in text


def test_overrides_win_over_the_environment() -> None:
    assert load_settings(role="worker").role == "worker"


def test_settings_are_read_once() -> None:
    first = get_settings()
    assert isinstance(first, Settings)
    assert get_settings() is first
