"""Random secrets and their SHA-256 hashes.

API tokens are 24 random bytes (URL-safe base64 after the prefix chk_), shown
once and stored only as SHA-256. A job's ping token is 24 random letters and
digits; it is part of the job's ping URL and shown with the job. Session
cookies carry 32 random bytes and the database keeps only their SHA-256 as the
session id.
"""

import hashlib
import secrets
import string

API_TOKEN_PREFIX = "chk_"
API_TOKEN_BYTES = 24
SESSION_SECRET_BYTES = 32
CSRF_TOKEN_BYTES = 32
PING_TOKEN_LENGTH = 24
_PING_ALPHABET = string.ascii_letters + string.digits


def new_api_token() -> str:
    """A new API token; the prefix lets secret scanners recognise it."""
    return API_TOKEN_PREFIX + secrets.token_urlsafe(API_TOKEN_BYTES)


def new_ping_token() -> str:
    """A job's ping token: 24 random letters and digits (about 143 bits)."""
    return "".join(secrets.choice(_PING_ALPHABET) for _ in range(PING_TOKEN_LENGTH))


def new_secret(nbytes: int = SESSION_SECRET_BYTES) -> str:
    """A URL-safe random value of nbytes random bytes."""
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    """The SHA-256 of a token or session secret, as stored in the database."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
