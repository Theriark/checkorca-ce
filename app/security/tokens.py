"""Random secrets and their SHA-256 hashes.

API tokens are 24 random bytes (URL-safe base64 after the prefix chk_), shown
once and stored only as SHA-256. Session cookies carry 32 random bytes and the
database keeps only their SHA-256 as the session id.
"""

import hashlib
import secrets

API_TOKEN_PREFIX = "chk_"
API_TOKEN_BYTES = 24
SESSION_SECRET_BYTES = 32
CSRF_TOKEN_BYTES = 32


def new_api_token() -> str:
    """A new API token; the prefix lets secret scanners recognise it."""
    return API_TOKEN_PREFIX + secrets.token_urlsafe(API_TOKEN_BYTES)


def new_secret(nbytes: int = SESSION_SECRET_BYTES) -> str:
    """A URL-safe random value of nbytes random bytes."""
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    """The SHA-256 of a token or session secret, as stored in the database."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
