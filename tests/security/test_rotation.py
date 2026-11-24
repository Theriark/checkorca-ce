"""FERNET_KEY rotation (phase C10): the stored secrets move to the new key
in one transaction, and only counts are ever said out loud.

Every _enc column of the release is covered: the IMAP password of an inbox,
the secret of a channel and the external heartbeat URL of the settings row.
"""

import base64
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.repos.inboxes import InboxRepository
from app.repos.notifications import ChannelRepository
from app.security.crypto import SecretBox
from app.security.rotation import RotationError, RotationReport, rotate_stored_secrets
from helpers import TEST_FERNET_KEY

OLD_KEY = TEST_FERNET_KEY
NEW_KEY = base64.urlsafe_b64encode(b"\x02" * 32).decode()
NOW = datetime(2027, 1, 4, 9, tzinfo=UTC)
INBOX_SECRET = "relay-password-000111"
CHANNEL_SECRET = "https://hooks.example.com/services/T000/B000/x"
HEARTBEAT_SECRET = "https://dead-man.example.com/ping?token=000111"


async def add_secrets(db_engine: AsyncEngine, box: SecretBox) -> None:
    """One row of each kind with a stored secret, and one channel without."""
    policy = AllowAllPolicy()
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        await InboxRepository(db, policy).create(
            SYSTEM,
            kind="imap",
            label="Vendor mailbox",
            now=NOW,
            imap_host="imap.example.com",
            imap_username="alerts",
            imap_password_enc=box.encrypt(INBOX_SECRET),
        )
        await ChannelRepository(db, policy).create(
            SYSTEM,
            kind="webhook",
            label="Ops hook",
            now=NOW,
            config={"url_set": True, "url_host": "hooks.example.com"},
            secret_enc=box.encrypt(CHANNEL_SECRET),
        )
        await ChannelRepository(db, policy).create(
            SYSTEM, kind="email", label="Ops mail", now=NOW, config={}
        )
        from app.repos.settings import SettingsRepository

        await SettingsRepository(db, policy, box).set_external_heartbeat_url(
            SYSTEM, HEARTBEAT_SECRET
        )
        await db.commit()


async def stored(db_engine: AsyncEngine) -> tuple[str | None, str | None, str | None]:
    """The raw ciphertext of the inbox password, the channel secret and the
    heartbeat URL, and nothing decrypted."""
    from sqlalchemy import select

    from app.db.models import AppSettings, Channel, Inbox

    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        inbox = (await db.scalars(select(Inbox))).one()
        query = select(Channel).where(Channel.secret_enc.is_not(None))
        channel = (await db.scalars(query)).one()
        row = (await db.scalars(select(AppSettings))).one()
        return (
            inbox.imap_password_enc,
            channel.secret_enc,
            row.external_heartbeat_url_enc,
        )


async def test_rotation_moves_every_secret_to_the_new_key(
    db_engine: AsyncEngine,
) -> None:
    """The round trip: rows the old key encrypted come out as ciphertext the
    new key alone can read, with the same values; a row without a secret
    stays NULL; the report counts one row of each kind."""
    await add_secrets(db_engine, SecretBox(OLD_KEY))
    before = await stored(db_engine)
    assert SecretBox(OLD_KEY).decrypt(before[0]) == INBOX_SECRET
    assert SecretBox(OLD_KEY).decrypt(before[1]) == CHANNEL_SECRET
    assert SecretBox(OLD_KEY).decrypt(before[2]) == HEARTBEAT_SECRET
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        report = await rotate_stored_secrets(db, SecretBox(NEW_KEY, OLD_KEY))
        await db.commit()
    assert report == RotationReport(inboxes=1, channels=1, settings=1)
    assert report.total == 3
    after = await stored(db_engine)
    fresh = SecretBox(NEW_KEY)
    assert after[0] != before[0] and after[1] != before[1]
    assert fresh.decrypt(after[0]) == INBOX_SECRET
    assert fresh.decrypt(after[1]) == CHANNEL_SECRET
    assert fresh.decrypt(after[2]) == HEARTBEAT_SECRET


async def test_a_missing_old_key_refuses_and_changes_nothing(
    db_engine: AsyncEngine,
) -> None:
    """Without the old key in FERNET_KEY the rotation refuses: no row was
    written and the stored secrets still read with the old key."""
    await add_secrets(db_engine, SecretBox(OLD_KEY))
    before = await stored(db_engine)
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        with pytest.raises(RotationError) as refused:
            await rotate_stored_secrets(db, SecretBox(NEW_KEY))
        await db.rollback()
    assert "cannot be decrypted" in str(refused.value)
    assert INBOX_SECRET not in str(refused.value)
    assert await stored(db_engine) == before
    assert SecretBox(OLD_KEY).decrypt(before[0]) == INBOX_SECRET
    assert SecretBox(OLD_KEY).decrypt(before[1]) == CHANNEL_SECRET
