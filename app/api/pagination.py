"""Cursor pagination: query cursor and limit (50, at most 200); answers carry
items and next_cursor. A cursor is opaque to clients: URL-safe base64 of JSON."""

import base64
import binascii
import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import Query

from app.api.problems import ProblemError

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
# Long enough for any cursor this API writes.
MAX_CURSOR_LENGTH = 512

LimitQuery = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
CursorQuery = Annotated[str | None, Query(max_length=MAX_CURSOR_LENGTH)]


def encode_cursor(values: dict[str, str]) -> str:
    raw = json.dumps(values, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, keys: tuple[str, ...]) -> dict[str, str]:
    """The values of a cursor this API wrote; 400 for anything else."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except (binascii.Error, UnicodeError, ValueError):
        values = None
    if (
        not isinstance(values, dict)
        or set(values) != set(keys)
        or not all(isinstance(value, str) for value in values.values())
    ):
        raise ProblemError(400, "Invalid cursor", "Use next_cursor as returned.")
    return {str(key): str(value) for key, value in values.items()}


def encode_time_cursor(key: str, at: datetime, row_id: uuid.UUID) -> str:
    """A cursor after the row with this time and id (lists ordered by both)."""
    return encode_cursor({key: at.isoformat(), "id": str(row_id)})


def decode_time_cursor(cursor: str, key: str) -> tuple[datetime, uuid.UUID]:
    values = decode_cursor(cursor, (key, "id"))
    invalid = ProblemError(400, "Invalid cursor", "Use next_cursor as returned.")
    try:
        at = datetime.fromisoformat(values[key])
        row_id = uuid.UUID(values["id"])
    except ValueError:
        raise invalid from None
    if at.utcoffset() is None:
        raise invalid
    return at, row_id
