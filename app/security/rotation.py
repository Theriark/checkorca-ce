"""FERNET_KEY rotation (phase C10, D-6): re-encrypt every stored secret.

FERNET_KEY may name more than one key, comma-separated, the new one first:
every key decrypts, the first encrypts (MultiFernet, app/security/crypto.py).
`python -m app rotate-fernet` re-encrypts every row of every column that
ends in _enc with the FIRST key, in ONE transaction: either every stored
secret moves to the new key, or nothing changes. After it succeeds the old
keys can be dropped from FERNET_KEY.

The command prints only counts. A key and a stored value never reach its
output or a log line; a row that no key of FERNET_KEY can decrypt raises
RotationError (the old key is missing from the setting), the transaction
rolls back and the command refuses with exit code 2.

The stored columns of this release: inbox.imap_password_enc,
channel.secret_enc and settings.external_heartbeat_url_enc.
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AppSettings, Channel, Inbox
from app.security.crypto import SecretBox, SecretBoxError

__all__ = ["RotationError", "RotationReport", "rotate_stored_secrets"]


class RotationError(ValueError):
    """A stored secret cannot be decrypted; FERNET_KEY is missing a key."""


@dataclass(frozen=True, slots=True)
class RotationReport:
    """How many rows of each table were re-encrypted, for the one-line answer."""

    inboxes: int = 0
    channels: int = 0
    settings: int = 0

    @property
    def total(self) -> int:
        return self.inboxes + self.channels + self.settings


def _re_encrypted(box: SecretBox, value: str) -> str:
    """The value as ciphertext of the first key; RotationError when no key of
    the box can read the stored one."""
    try:
        return box.encrypt(box.decrypt(value))
    except SecretBoxError:
        raise RotationError(
            "a stored credential cannot be decrypted with FERNET_KEY; keep "
            "every old key in the setting until the rotation has run"
        ) from None


async def _rotate(db: AsyncSession, model: Any, column: Any, box: SecretBox) -> int:
    """Re-encrypt every not-null value of the column; the number of rows."""
    rows = (await db.scalars(select(model).where(column.is_not(None)))).all()
    for row in rows:
        setattr(row, column.key, _re_encrypted(box, getattr(row, column.key)))
    return len(rows)


async def rotate_stored_secrets(db: AsyncSession, box: SecretBox) -> RotationReport:
    """Re-encrypt every stored secret with the box's first key, in the
    caller's transaction (the caller commits)."""
    return RotationReport(
        inboxes=await _rotate(db, Inbox, Inbox.imap_password_enc, box),
        channels=await _rotate(db, Channel, Channel.secret_enc, box),
        settings=await _rotate(
            db, AppSettings, AppSettings.external_heartbeat_url_enc, box
        ),
    )
