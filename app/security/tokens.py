"""Random secrets and their SHA-256 hashes.

API tokens are 24 random bytes (URL-safe base64 after the prefix chk_), shown
once and stored only as SHA-256. A job's ping token is 24 random letters and
digits; it is part of the job's ping URL and shown with the job. Session
cookies carry 32 random bytes and the database keeps only their SHA-256 as the
session id. An inbox code is 24 random lower-case letters and digits (the
local part of an inbox address, so case must not matter); a webhook inbox's
token is 24 random bytes after the prefix chki_, shown once and stored as
SHA-256 like an API token.
"""

import hashlib
import secrets
import string

API_TOKEN_PREFIX = "chk_"
API_TOKEN_BYTES = 24
SESSION_SECRET_BYTES = 32
CSRF_TOKEN_BYTES = 32
PING_TOKEN_LENGTH = 24
INBOX_CODE_LENGTH = 24
INBOX_TOKEN_PREFIX = "chki_"
_PING_ALPHABET = string.ascii_letters + string.digits
_CODE_ALPHABET = string.ascii_lowercase + string.digits


def new_api_token() -> str:
    """A new API token; the prefix lets secret scanners recognise it."""
    return API_TOKEN_PREFIX + secrets.token_urlsafe(API_TOKEN_BYTES)


def new_ping_token() -> str:
    """A job's ping token: 24 random letters and digits (about 143 bits)."""
    return "".join(secrets.choice(_PING_ALPHABET) for _ in range(PING_TOKEN_LENGTH))


def new_inbox_code() -> str:
    """An inbox code: 24 random lower-case letters and digits (about 124 bits)."""
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(INBOX_CODE_LENGTH))


def new_inbox_token() -> str:
    """A webhook inbox's token; its own prefix tells it from an API token."""
    return INBOX_TOKEN_PREFIX + secrets.token_urlsafe(API_TOKEN_BYTES)


def new_secret(nbytes: int = SESSION_SECRET_BYTES) -> str:
    """A URL-safe random value of nbytes random bytes."""
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    """The SHA-256 of a token or session secret, as stored in the database."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
