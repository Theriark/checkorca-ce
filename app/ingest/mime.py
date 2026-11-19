"""Reading a received message: headers, Message-ID, content hash and text.

Every message is hostile (rnd-report-2 5.9). Nothing here follows a link,
loads a remote part or keeps an attachment; text comes out as plain text with
invalid bytes replaced and NUL characters removed (PostgreSQL text and JSONB
refuse them).
"""

import hashlib
import re
from email.errors import HeaderParseError
from email.header import decode_header, make_header
from email.message import Message
from email.parser import BytesParser
from email.policy import compat32
from typing import Final

from app.db.models import MESSAGE_ID_LENGTH

MAX_HEADERS: Final = 200
MAX_HEADER_NAME: Final = 200
MAX_HEADER_VALUE: Final = 4000
# The text a message detail shows; the parser engine caps its input at 256 KB.
MAX_TEXT: Final = 256 * 1024

_FOLD = re.compile(r"\r?\n[ \t]+")
_LINE_BREAK = re.compile(r"\r?\n")


def clean_text(text: str) -> str:
    """Valid UTF-8 text: undecodable bytes become U+FFFD, NUL is removed."""
    try:
        data = text.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        data = text.encode("utf-8", "replace")
    return data.decode("utf-8", "replace").replace("\x00", "")


def header_value(value: object) -> str:
    """A header value unfolded and decoded (RFC 2047 encoded words)."""
    text = _FOLD.sub(" ", str(value))
    try:
        text = str(make_header(decode_header(text)))
    except (HeaderParseError, LookupError, UnicodeError, ValueError):
        pass
    return clean_text(_LINE_BREAK.sub(" ", text))


def parse_headers(raw: bytes) -> Message:
    return BytesParser(policy=compat32).parsebytes(raw, headersonly=True)


def header_list(message: Message) -> list[list[str]]:
    """[[name, value], ...] in the order received, at most MAX_HEADERS."""
    return [
        [clean_text(name)[:MAX_HEADER_NAME], header_value(value)[:MAX_HEADER_VALUE]]
        for name, value in message.items()[:MAX_HEADERS]
    ]


def message_id(message: Message) -> str | None:
    """The Message-ID header as sent, or None when absent, empty or too long."""
    value = message.get("Message-ID")
    if value is None:
        return None
    found = clean_text(_FOLD.sub(" ", str(value))).strip()
    if not found or len(found) > MESSAGE_ID_LENGTH:
        return None
    return found


def body_of(raw: bytes) -> bytes:
    """The bytes after the blank line that ends the headers."""
    ends = [
        (index, len(separator))
        for separator in (b"\r\n\r\n", b"\n\n")
        if (index := raw.find(separator)) >= 0
    ]
    if not ends:
        return b""
    index, length = min(ends)
    return raw[index + length :]


def content_hash(raw: bytes, message: Message) -> str:
    """The duplicate key besides the Message-ID: SHA-256 of the Date header and
    the body, line endings normalised.

    The Date header is part of it so that a script that sends the same text
    every day is not taken for a duplicate of yesterday's mail, while the same
    message delivered twice (or forwarded with a new Message-ID) is.
    """
    date = header_value(message.get("Date", "")).strip()
    body = body_of(raw).replace(b"\r\n", b"\n")
    return hashlib.sha256(b"date:" + date.encode("utf-8") + b"\n" + body).hexdigest()


def _text_part(message: Message) -> Message | None:
    """The first inline text/plain part, else the first inline text/html part."""
    html: Message | None = None
    for part in message.walk():
        if part.is_multipart():
            continue
        if part.get_content_disposition() == "attachment":
            continue
        kind = part.get_content_type()
        if kind == "text/plain":
            return part
        if kind == "text/html" and html is None:
            html = part
    return html


def message_text(raw: bytes) -> tuple[str, bool]:
    """The readable text of a message and whether it was cut at MAX_TEXT.

    An HTML-only message gives its HTML source as text until the stripper of
    phase C4-I (app/ingest/html_text.py) turns it into text. Callers show it
    escaped, never as HTML.
    """
    part = _text_part(BytesParser(policy=compat32).parsebytes(raw))
    if part is None:
        return "", False
    payload = part.get_payload(decode=True)
    if not isinstance(payload, bytes):
        return "", False
    charset = part.get_content_charset() or "utf-8"
    try:
        text = payload.decode(charset, "replace")
    except LookupError:
        text = payload.decode("utf-8", "replace")
    text = clean_text(text)
    return text[:MAX_TEXT], len(text) > MAX_TEXT
