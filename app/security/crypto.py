"""Fernet encryption of stored credentials, and masked hints (D-6).

Columns ending in _enc hold Fernet ciphertext made with FERNET_KEY. The API
never returns a stored credential: forms show whether one is set and, at most,
a masked hint with its last four characters.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

MASK = "****"
# Below this length the last four characters would give too much away.
MIN_HINT_LENGTH = 12


class SecretBoxError(ValueError):
    """Stored ciphertext could not be decrypted with the configured key."""


class SecretBox:
    """Encrypt and decrypt stored credentials.

    The first key encrypts; every key can decrypt, so a key rotation (phase C10)
    can re-encrypt with a new key while old rows still read.
    """

    def __init__(self, *keys: str) -> None:
        if not keys:
            raise ValueError("SecretBox needs at least one Fernet key")
        self._fernet = MultiFernet([Fernet(key) for key in keys])

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf-8")).decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self._fernet.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except (InvalidToken, UnicodeError):
            # No chained exception: it adds nothing and keeps logs short.
            raise SecretBoxError(
                "a stored credential cannot be decrypted with FERNET_KEY"
            ) from None


def mask_hint(secret: str | None) -> str | None:
    """None when nothing is stored, else **** plus the last four characters."""
    if not secret:
        return None
    if len(secret) < MIN_HINT_LENGTH:
        return MASK
    return MASK + secret[-4:]
