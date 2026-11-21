"""messages: list received messages and read one.

Every message is hostile (rnd-report-2 5.9): the detail gives its headers and
text as plain strings for the web app to show escaped, never as HTML, and no
attachment content. Admins and technicians, or an API token of scope read.
"""

import asyncio
import uuid
from typing import Annotated, cast

from fastapi import APIRouter, Query

from app.api.deps import DbDep, ReaderDep, ServicesDep
from app.api.pagination import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_time_cursor,
    encode_time_cursor,
)
from app.api.problems import ProblemError
from app.api.v1.ingest_schemas import (
    HeaderOut,
    MessageDetail,
    MessageOut,
    MessagePage,
    ParseState,
    ResultOut,
)
from app.db.models import RawMessage
from app.ingest.mime import message_text
from app.ingest.store import raw_bytes
from app.repos.messages import RawMessageRepository
from app.repos.results import JobResultRepository

router = APIRouter(prefix="/messages", tags=["messages"])

StateQuery = Annotated[ParseState | None, Query()]


def first_header(message: RawMessage, name: str) -> str | None:
    for header_name, value in message.headers:
        if header_name.casefold() == name:
            return value
    return None


def message_out(message: RawMessage) -> MessageOut:
    return MessageOut(
        id=message.id,
        inbox_id=message.inbox_id,
        client_id=message.client_id,
        received_at=message.received_at,
        message_id=message.message_id,
        size=message.size,
        parse_state=cast(ParseState, message.parse_state),
        parsed_at=message.parsed_at,
        parse_pack_id=message.parse_pack_id,
        parse_reason=message.parse_reason,
        parse_path=message.parse_path,
        subject=first_header(message, "subject"),
        sender=first_header(message, "from"),
    )


@router.get("")
async def list_messages(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    inbox_id: uuid.UUID | None = None,
    parse_state: StateQuery = None,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> MessagePage:
    """Messages, newest first."""
    after = None if cursor is None else decode_time_cursor(cursor, "received_at")
    messages = RawMessageRepository(db, services.policy)
    found = await messages.page(
        principal,
        inbox_id=inbox_id,
        parse_state=parse_state,
        after=after,
        limit=limit + 1,
    )
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        last = items[-1]
        next_cursor = encode_time_cursor("received_at", last.received_at, last.id)
    return MessagePage(
        items=[message_out(message) for message in items], next_cursor=next_cursor
    )


@router.get("/{message_id}")
async def get_message(
    message_id: uuid.UUID, principal: ReaderDep, services: ServicesDep, db: DbDep
) -> MessageDetail:
    """One message: headers, readable text (at most 256 KB) and its results."""
    messages = RawMessageRepository(db, services.policy)
    message = await messages.get(principal, message_id)
    if message is None:
        raise ProblemError(404, "Message not found")
    results = await JobResultRepository(db, services.policy).page(
        principal, raw_message_id=message.id, limit=MAX_LIMIT
    )
    # Up to 5 MB of MIME: decoded off the event loop.
    raw = await asyncio.to_thread(raw_bytes, message.body_zlib)
    text, truncated = await asyncio.to_thread(message_text, raw)
    return MessageDetail(
        **message_out(message).model_dump(),
        headers=[HeaderOut(name=name, value=value) for name, value in message.headers],
        text=text,
        text_truncated=truncated,
        results=[ResultOut.model_validate(result) for result in results],
    )
