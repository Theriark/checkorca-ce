"""Reading a received message: headers, Message-ID, content hash and text.

Every message is hostile (rnd-report-2 5.9). Nothing here follows a link,
loads a remote part or keeps an attachment; text comes out as plain text with
invalid bytes replaced and NUL characters removed (PostgreSQL text and JSONB
refuse them).
"""

import hashlib
import re
import secrets
from email.errors import HeaderParseError
from email.header import decode_header, make_header
from email.message import Message
from email.parser import BytesParser
from email.policy import compat32
from typing import Final

from app.db.models import MESSAGE_ID_LENGTH
from app.ingest.html_text import html_to_text

MAX_HEADERS: Final = 200
MAX_HEADER_NAME: Final = 200
MAX_HEADER_VALUE: Final = 4000
# RFC 2047 decoding (email.header.decode_header) is quadratic in its input, so
# a value is cut to this many characters before it is decoded.
MAX_DECODED_INPUT: Final = 2 * MAX_HEADER_VALUE
# The header block of a message; a longer one is refused by every receiver.
MAX_HEADER_BYTES: Final = 256 * 1024
# The text a message detail shows; the parser engine caps its input at 256 KB.
MAX_TEXT: Final = 256 * 1024
# HTML given to the stripper; the visible text of more is not needed.
MAX_HTML_INPUT: Final = 1024 * 1024
# Besides the body, what tells one alert from another for the duplicate key.
CONTENT_HEADERS: Final = ("Date", "From", "To", "Subject")

_FOLD = re.compile(r"\r?\n[ \t]+")
_LINE_BREAK = re.compile(r"\r?\n")


def clean_text(text: str) -> str:
    """Valid UTF-8 text: undecodable bytes become U+FFFD, NUL is removed."""
    try:
        data = text.encode("utf-8", "surrogateescape")
    except UnicodeEncodeError:
        data = text.encode("utf-8", "replace")
    return data.decode("utf-8", "replace").replace("\x00", "")


def raw_header_value(value: object) -> str | None:
    """A structured header value unfolded, without RFC 2047 decoding: encoded
    words mean nothing in a structured header such as Authentication-Results,
    and decoding them first could add separators to it. None when it is longer
    than MAX_DECODED_INPUT characters: a cut value could end inside a domain
    (header.d=example.com.attacker.test read as example.com), so it is read
    whole or not at all."""
    text = _FOLD.sub(" ", str(value))
    if len(text) > MAX_DECODED_INPUT:
        return None
    return clean_text(_LINE_BREAK.sub(" ", text))


def header_value(value: object) -> str:
    """A header value unfolded and decoded (RFC 2047 encoded words), from at
    most MAX_DECODED_INPUT characters of it."""
    text = _FOLD.sub(" ", str(value))[:MAX_DECODED_INPUT]
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


def _header_end(raw: bytes) -> tuple[int, int] | None:
    """Where the blank line that ends the headers starts, and its length."""
    ends = [
        (index, len(separator))
        for separator in (b"\r\n\r\n", b"\n\n")
        if (index := raw.find(separator)) >= 0
    ]
    return min(ends) if ends else None


def header_bytes(raw: bytes) -> int:
    """The length of the header block; all of raw when no blank line ends it."""
    end = _header_end(raw)
    return len(raw) if end is None else end[0]


def body_of(raw: bytes) -> bytes:
    """The bytes after the blank line that ends the headers."""
    end = _header_end(raw)
    if end is None:
        return b""
    index, length = end
    return raw[index + length :]


def content_hash(raw: bytes, message: Message) -> str:
    """The duplicate key besides the Message-ID: SHA-256 of the Date, From, To
    and Subject headers and the body, line endings normalised.

    The same message delivered twice, or forwarded with a new Message-ID, has
    the same key. Two alerts that differ only in the Subject (the status in
    the Subject, an empty body) do not, nor does the same text on another day.
    A message without a Date header gets a key of its own: only its
    Message-ID can make it a duplicate, so a script that sends the same words
    without a Date is never taken for an earlier run.
    """
    if not header_value(message.get("Date", "")).strip():
        return hashlib.sha256(b"no-date:" + secrets.token_bytes(32)).hexdigest()
    parts: list[bytes] = []
    for name in CONTENT_HEADERS:
        value = header_value(message.get(name, "")).strip()
        parts.append(f"{name.lower()}:{value}".encode())
    body = body_of(raw).replace(b"\r\n", b"\n")
    return hashlib.sha256(b"\n".join([*parts, body])).hexdigest()


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

    An HTML-only message gives the visible text of its HTML part
    (app/ingest/html_text.py, the first MAX_HTML_INPUT characters), never the
    markup. Callers show it escaped.
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
    if part.get_content_type() == "text/html":
        text = html_to_text(text[:MAX_HTML_INPUT])
    text = clean_text(text)
    return text[:MAX_TEXT], len(text) > MAX_TEXT
