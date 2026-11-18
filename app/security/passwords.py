"""Argon2id password hashes (argon2-cffi defaults: the RFC 9106 low-memory profile).

Hashing runs in a worker thread so the event loop keeps serving. Each hash holds
64 MiB while it runs, so at most two run at once: a 384 MB container stays safe
under a burst of sign-in attempts.
"""

import asyncio

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

MIN_PASSWORD_LENGTH = 12
# Bounds the work an attacker can ask for with one request.
MAX_PASSWORD_LENGTH = 128
MAX_CONCURRENT_HASHES = 2
# Verified when the e-mail address is unknown, so both answers take as long.
_TIMING_PASSWORD = "checkorca-timing-equaliser"


class PasswordService:
    """Hash and verify passwords without blocking the event loop."""

    def __init__(self, hasher: PasswordHasher | None = None) -> None:
        self._hasher = hasher or PasswordHasher()
        self._slots = asyncio.Semaphore(MAX_CONCURRENT_HASHES)
        self._timing_hash: str | None = None

    async def hash(self, password: str) -> str:
        async with self._slots:
            return await asyncio.to_thread(self._hasher.hash, password)

    async def verify(self, password_hash: str, password: str) -> bool:
        """True when the password matches; a malformed hash never matches."""
        async with self._slots:
            return await asyncio.to_thread(self._verify, password_hash, password)

    def needs_rehash(self, password_hash: str) -> bool:
        """True when the hash was made with weaker parameters than today's."""
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except InvalidHashError:
            return True

    async def spend_verify_time(self, password: str) -> None:
        """Do the work of one verification for an unknown or disabled account."""
        if self._timing_hash is None:
            self._timing_hash = await self.hash(_TIMING_PASSWORD)
        await self.verify(self._timing_hash, password)

    def _verify(self, password_hash: str, password: str) -> bool:
        try:
            return self._hasher.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False
