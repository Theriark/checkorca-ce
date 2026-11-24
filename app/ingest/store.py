"""The raw message store and the result recorder every ingest channel calls.

store_raw keeps one received message: at most 5 MB, SHA-256 of the bytes,
zlib-compressed, with its decoded headers, kept until purge_after (received_at
plus settings.retention_raw_days). The same Message-ID or the same content
hash (app/ingest/mime.py) in the same inbox is stored once and counted once.

record_result keeps one run (a ParsedResult) of a parsed message, a ping or
the results API.

Both work in the caller's transaction and never commit: the SMTP listener
answers 250, the IMAP poller marks a message seen and the HTTP routes answer
202 only after their own commit. Both go through the repositories, so the
caller's Principal and the AccessPolicy decide (receivers run as SYSTEM).
"""

import json
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
from typing import Any, Final

from sqlalchemy.ext.asyncio import AsyncSession

from app.access import AccessPolicy, Principal
from app.db.models import NAME_LENGTH
from app.ingest import mime
from app.ingest.results import RESULT_STATUSES, ParsedResult
from app.ops.metrics import MESSAGES_RECEIVED, RESULTS
from app.repos.inboxes import InboxRepository
from app.repos.messages import RawMessageRepository
from app.repos.results import JobResultRepository

# rnd-report-2 5.7: 5 MB per message, on every channel.
MAX_MESSAGE_BYTES: Final = 5 * 1024 * 1024
# The details of one result, as JSON.
MAX_DETAILS_BYTES: Final = 16 * 1024


class MessageTooLarge(ValueError):
    """The message is larger than MAX_MESSAGE_BYTES; nothing was stored."""


class ResultRejected(ValueError):
    """The result cannot be stored as given; the text says which field."""


@dataclass(frozen=True, slots=True)
class StoredRaw:
    """The stored message's id; duplicate means an earlier row of the same
    inbox already had it and nothing new was stored."""

    id: uuid.UUID
    duplicate: bool


async def store_raw(
    db: AsyncSession,
    policy: AccessPolicy,
    principal: Principal,
    *,
    inbox_id: uuid.UUID,
    raw: bytes,
    received_at: datetime,
) -> StoredRaw:
    """Store one received message of the inbox (RFC 822 bytes as received).

    Raises MessageTooLarge above 5 MB. Does not commit.
    """
    if len(raw) > MAX_MESSAGE_BYTES:
        raise MessageTooLarge(f"a message may have at most {MAX_MESSAGE_BYTES} bytes")
    MESSAGES_RECEIVED.inc()
    headers = mime.parse_headers(raw)
    message_id = mime.message_id(headers)
    body_sha256 = mime.content_hash(raw, headers)
    messages = RawMessageRepository(db, policy)
    keep = timedelta(days=await messages.keep_days(principal))
    # A duplicate found by the insert can be purged before the lookup; then the
    # second insert stores the message.
    for _ in range(2):
        stored = await messages.insert(
            principal,
            inbox_id=inbox_id,
            received_at=received_at,
            message_id=message_id,
            sha256=sha256(raw).hexdigest(),
            body_sha256=body_sha256,
            size=len(raw),
            headers=mime.header_list(headers),
            body_zlib=zlib.compress(raw),
            purge_after=received_at + keep,
        )
        if stored is not None:
            inboxes = InboxRepository(db, policy)
            await inboxes.mark_received(principal, inbox_id, received_at)
            return StoredRaw(id=stored, duplicate=False)
        earlier = await messages.find_duplicate(
            principal,
            inbox_id=inbox_id,
            message_id=message_id,
            body_sha256=body_sha256,
        )
        if earlier is not None:
            return StoredRaw(id=earlier, duplicate=True)
    raise RuntimeError("the message was neither stored nor found as a duplicate")


def raw_bytes(body_zlib: bytes) -> bytes:
    """The stored message, decompressed, never more than MAX_MESSAGE_BYTES."""
    inflater = zlib.decompressobj()
    data = inflater.decompress(body_zlib, MAX_MESSAGE_BYTES + 1)
    if len(data) > MAX_MESSAGE_BYTES:
        raise MessageTooLarge("the stored message is larger than allowed")
    return data


def _text(value: str | None, field: str) -> str | None:
    if value is None:
        return None
    text = mime.clean_text(" ".join(value.split()))
    if len(text) > NAME_LENGTH:
        raise ResultRejected(f"{field} must be at most {NAME_LENGTH} characters")
    return text or None


def _time(value: datetime | None, field: str) -> datetime | None:
    if value is not None and value.utcoffset() is None:
        raise ResultRejected(f"{field} must carry a time zone")
    return value


def _has_nul(value: Any) -> bool:
    """A NUL character in a key or a string value, at any depth."""
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, dict):
        return any(_has_nul(key) or _has_nul(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_nul(item) for item in value)
    return False


def _details(details: Any) -> dict[str, Any]:
    if not isinstance(details, dict):
        raise ResultRejected("details must be an object")
    try:
        encoded = json.dumps(details, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise ResultRejected("details must hold JSON values only") from None
    loaded: dict[str, Any] = json.loads(encoded)
    # PostgreSQL JSONB refuses NUL; checked on the values, so a text holding
    # a backslash and "u0000" (a Windows path, say) is still accepted. Checked
    # on what is stored, where a tuple has become a list (THE-2011 note 1).
    if _has_nul(loaded):
        raise ResultRejected("details must not contain NUL characters")
    try:
        size = len(encoded.encode("utf-8"))
    except UnicodeEncodeError:
        # A lone surrogate, which a JSON body can carry as an escape.
        raise ResultRejected("details must be valid Unicode text") from None
    if size > MAX_DETAILS_BYTES:
        raise ResultRejected(f"details may have at most {MAX_DETAILS_BYTES} bytes")
    return loaded


async def record_result(
    db: AsyncSession,
    policy: AccessPolicy,
    principal: Principal,
    result: ParsedResult,
    *,
    received_at: datetime,
    job_id: uuid.UUID | None = None,
    raw_message_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Store one result; job_id when the job is known (ping, results API with
    job_id), else NULL until the matcher binds it. Raises ResultRejected for a
    value the table cannot hold. Does not commit."""
    if result.status not in RESULT_STATUSES:
        raise ResultRejected(f"status must be one of {', '.join(RESULT_STATUSES)}")
    results = JobResultRepository(db, policy)
    row = await results.create(
        principal,
        job_id=job_id,
        client_hint=_text(result.client_hint, "client_hint"),
        job_name=_text(result.job_name, "job_name"),
        status=result.status,
        started_at=_time(result.started_at, "started_at"),
        finished_at=_time(result.finished_at, "finished_at"),
        received_at=received_at,
        raw_message_id=raw_message_id,
        run_id=_text(result.run_id, "run_id"),
        details=_details(dict(result.details)),
    )
    RESULTS.labels(status=result.status).inc()
    return row.id
