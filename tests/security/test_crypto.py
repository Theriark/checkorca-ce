"""Fernet helpers: stored credentials are ciphertext in the database (D-6)."""

import base64

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.repos.settings import SettingsRepository
from app.security.crypto import SecretBox, SecretBoxError, mask_hint
from helpers import TEST_FERNET_KEY

OTHER_KEY = base64.urlsafe_b64encode(bytes(range(32))).decode()
# A synthetic heartbeat URL with its own path secret (legal R-11: example.com).
HEARTBEAT_URL = "https://hc.example.com/ping/synthetic-check-0001"
STORED_COLUMN = text("SELECT external_heartbeat_url_enc FROM settings")
WHOLE_ROW = text("SELECT row_to_json(s)::text FROM settings s")


def test_round_trip_and_fresh_ciphertext() -> None:
    box = SecretBox(TEST_FERNET_KEY)
    first = box.encrypt(HEARTBEAT_URL)
    second = box.encrypt(HEARTBEAT_URL)
    assert first != second
    assert HEARTBEAT_URL not in first
    assert box.decrypt(first) == box.decrypt(second) == HEARTBEAT_URL


def test_another_key_cannot_decrypt() -> None:
    ciphertext = SecretBox(TEST_FERNET_KEY).encrypt(HEARTBEAT_URL)
    with pytest.raises(SecretBoxError) as caught:
        SecretBox(OTHER_KEY).decrypt(ciphertext)
    assert caught.value.__cause__ is None
    with pytest.raises(SecretBoxError):
        SecretBox(OTHER_KEY).decrypt("not ciphertext")


def test_older_keys_still_decrypt_after_a_rotation() -> None:
    old = SecretBox(OTHER_KEY).encrypt(HEARTBEAT_URL)
    rotated = SecretBox(TEST_FERNET_KEY, OTHER_KEY)
    assert rotated.decrypt(old) == HEARTBEAT_URL
    assert SecretBox(TEST_FERNET_KEY).decrypt(rotated.encrypt("x" * 20)) == "x" * 20


def test_a_box_needs_a_key() -> None:
    with pytest.raises(ValueError):
        SecretBox()


@pytest.mark.parametrize(
    ("secret", "hint"),
    [
        (None, None),
        ("", None),
        ("short-value", "****"),
        ("long-synthetic-value-wxyz", "****wxyz"),
    ],
)
def test_masked_hints(secret: str | None, hint: str | None) -> None:
    assert mask_hint(secret) == hint


async def test_the_database_holds_only_ciphertext(db_engine: AsyncEngine) -> None:
    box = SecretBox(TEST_FERNET_KEY)
    sessionmaker = async_sessionmaker(db_engine, expire_on_commit=False)
    async with sessionmaker() as db:
        repository = SettingsRepository(db, AllowAllPolicy(), box)
        await repository.set_external_heartbeat_url(SYSTEM, HEARTBEAT_URL)
        await db.commit()

    async with db_engine.connect() as connection:
        stored = (await connection.execute(STORED_COLUMN)).scalar_one()
        dump = (await connection.execute(WHOLE_ROW)).scalar_one()
    assert stored and HEARTBEAT_URL not in stored
    assert "synthetic-check-0001" not in dump
    assert box.decrypt(stored) == HEARTBEAT_URL

    async with sessionmaker() as db:
        repository = SettingsRepository(db, AllowAllPolicy(), box)
        assert await repository.external_heartbeat_url(SYSTEM) == HEARTBEAT_URL
        settings = await repository.get(SYSTEM)
        assert settings.digest_timezone == "Europe/Lisbon"
        assert settings.retention_raw_days == 30
        await repository.set_external_heartbeat_url(SYSTEM, None)
        await db.commit()
        assert await repository.external_heartbeat_url(SYSTEM) is None
