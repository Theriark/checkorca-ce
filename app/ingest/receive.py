"""What every receiver does with a message for one inbox: check, then store.

The SMTP listener, the IMAP poller, POST ingest/email and the .eml upload all
call accept_message, so the same rules hold on every channel:

1. At most 5 MB, of which at most 256 KB of headers (MessageTooLarge).
2. The inbox's sender allowlist: when it is not empty, every address of the
   From header must be listed, as itself (alerts@example.com) or by its domain
   (@example.com). A message without a From address is refused.
3. With require_auth_results, the topmost Authentication-Results header must
   report dkim=pass for the From domain or a parent domain of it. That header
   is written by the mail server that received the message, so the check is
   only as good as that server: a sender that talks to the SMTP listener
   directly writes its own (docs/ingest.md, Sender checks).
4. store_raw in the caller's transaction; duplicates are stored once.

A refused message raises MessageRefused and stores nothing. Its reason is a
fixed word for logs and answers, never an address. Steps 1 to 3 parse
untrusted headers, so accept_message runs them in a thread: the event loop
keeps serving the other senders meanwhile.
"""

import asyncio
import re
from datetime import datetime
from email.message import Message
from email.utils import getaddresses
from typing import Final, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.access import AccessPolicy, Principal
from app.db.models import Inbox
from app.ingest import mime
from app.ingest.store import MAX_MESSAGE_BYTES, MessageTooLarge, StoredRaw, store_raw

RefusalReason = Literal["sender", "authentication"]

# An RFC 5322 quoted string, as in a quoted local part ("a@example.com"@x.test),
# or an RFC 8601 comment without nesting, whichever starts first.
_QUOTED_OR_COMMENT = re.compile(r'"((?:[^"\\]|\\.)*)"|\((?:[^()\\]|\\.)*\)')
# What comes just before a quoted string that is a whole header.d or header.i
# value (RFC 8601 allows header.d="example.com"); the window it is looked for in.
_PROPERTY_BEFORE = re.compile(r"\bheader\.[di]\s*=\s*$", re.IGNORECASE)
_PROPERTY_WINDOW: Final = 32
# What may follow such a whole value (RFC 8601): CFWS, then the end, a ";" or
# the next ptype.property=. After a local part an @ or a "." follows instead
# ("a@example.com" (x) @attacker.test), so a quoted local part stays opaque.
_VALUE_END = re.compile(
    r"(?:\s|\((?:[^()\\]|\\.)*\))*(?:$|;|[A-Za-z][A-Za-z0-9-]*\.[A-Za-z0-9-]+\s*=)"
)
_PLAIN_VALUE = re.compile(r"(?:[A-Za-z0-9._+-]+@)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*")
_DKIM_PASS = re.compile(r"^\s*dkim\s*=\s*pass\b", re.IGNORECASE)
# header.d (the signing domain) and header.i (the AUID, local part optional).
_DKIM_PROPERTY = re.compile(r"\bheader\.([di])\s*=\s*([^\s;]+)", re.IGNORECASE)
_DOMAIN = re.compile(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*")
MAIL_HEADERS: Final = ("From", "Subject", "Date", "Message-ID")
REFUSAL_TEXT: Final[dict[RefusalReason, str]] = {
    "sender": "The sender is not on the inbox's sender allowlist.",
    "authentication": "No Authentication-Results dkim=pass for the sender's domain.",
}


class MessageRefused(ValueError):
    """The inbox's rules refuse the message; nothing was stored."""

    def __init__(self, reason: RefusalReason) -> None:
        super().__init__(REFUSAL_TEXT[reason])
        self.reason: RefusalReason = reason


def from_addresses(headers: Message) -> list[str]:
    """The addresses of the From header, lower case; [] when it has none."""
    values = [mime.header_value(value) for value in headers.get_all("From", [])]
    return [
        address.strip().lower()
        for _, address in getaddresses(values)
        if "@" in address and address.strip()
    ]


def sender_allowed(allowlist: list[str], addresses: list[str]) -> bool:
    """True when the allowlist is empty or names every address or its domain."""
    if not allowlist:
        return True
    allowed = set(allowlist)
    return bool(addresses) and all(
        address in allowed or "@" + address.rpartition("@")[2] in allowed
        for address in addresses
    )


def _aligned(signer: str, domain: str) -> bool:
    signer = signer.strip(".").lower()
    return domain == signer or domain.endswith("." + signer)


def masked(value: str) -> str | None:
    """The Authentication-Results text with every comment a space and every
    quoted string the opaque word q, in one left-to-right pass, so nothing
    inside them is read as a separator, a property or a domain. A quoted
    string that is a whole header.d or header.i value (only CFWS, then the
    end, a ";" or the next property after it) and a plain domain or AUID
    keeps its text. None when a quote or a parenthesis is left over (an
    unbalanced quote or a nested comment): the header is not trusted."""

    def replace(match: re.Match[str]) -> str:
        text = match.group(1)
        if text is None:
            return " "
        start = match.start()
        before = value[max(0, start - _PROPERTY_WINDOW) : start]
        if (
            _PROPERTY_BEFORE.search(before)
            and _VALUE_END.match(value, match.end())
            and _PLAIN_VALUE.fullmatch(text)
        ):
            return text
        return "q"

    result = _QUOTED_OR_COMMENT.sub(replace, value)
    return None if any(char in result for char in '"()') else result


def dkim_signer(result: str) -> str | None:
    """The signing domain of one dkim=pass result: header.d, else the domain
    of header.i (after its last @, never its local part). Quoted strings and
    comments are masked first (see masked); a header.i without an @ is no
    AUID and counts for nothing."""
    text = masked(result)
    if text is None:
        return None
    properties: dict[str, str] = {}
    for name, value in _DKIM_PROPERTY.findall(text):
        properties.setdefault(name.lower(), value)
    if "d" in properties:
        domain = properties["d"]
    elif "@" in properties.get("i", ""):
        domain = properties["i"].rpartition("@")[2]
    else:
        return None
    return domain if _DOMAIN.fullmatch(domain) else None


def dkim_passed(headers: Message, addresses: list[str]) -> bool:
    """The topmost Authentication-Results reports dkim=pass for a domain the
    From addresses belong to (relaxed alignment, RFC 7489 3.1.1)."""
    results = headers.get_all("Authentication-Results", [])
    if not results or not addresses:
        return False
    # Parsed as sent and whole: no encoded-word decoding, no cut value, and
    # quoted strings and comments masked before the split, so neither can
    # add a ";".
    raw = mime.raw_header_value(results[0])
    value = None if raw is None else masked(raw)
    if value is None:
        return False
    # The first item is the authserv-id; the results follow, one per ";".
    signers = []
    for item in value.split(";")[1:]:
        if _DKIM_PASS.match(item) and (signer := dkim_signer(item)):
            signers.append(signer)
    domains = {address.rpartition("@")[2] for address in addresses}
    return all(
        any(_aligned(signer, domain) for signer in signers) for domain in domains
    )


def is_mail(raw: bytes) -> bool:
    """True when the bytes start with a header block that names at least one
    of From, Subject, Date or Message-ID: an upload or an HTTP body that is
    no e-mail message at all is refused instead of stored."""
    headers = mime.parse_headers(raw)
    return any(headers.get(name) for name in MAIL_HEADERS)


def check_size(raw: bytes) -> None:
    """Raise MessageTooLarge above 5 MB, or above 256 KB of headers."""
    if len(raw) > MAX_MESSAGE_BYTES:
        raise MessageTooLarge(f"a message may have at most {MAX_MESSAGE_BYTES} bytes")
    if mime.header_bytes(raw) > mime.MAX_HEADER_BYTES:
        raise MessageTooLarge(
            f"the headers may have at most {mime.MAX_HEADER_BYTES} bytes"
        )


def check_rules(raw: bytes, allowlist: list[str], require_auth_results: bool) -> None:
    """check_message with the inbox's rules as plain values (thread-safe)."""
    check_size(raw)
    if not allowlist and not require_auth_results:
        return
    headers = mime.parse_headers(raw)
    addresses = from_addresses(headers)
    if not sender_allowed(allowlist, addresses):
        raise MessageRefused("sender")
    if require_auth_results and not dkim_passed(headers, addresses):
        raise MessageRefused("authentication")


def check_message(inbox: Inbox, raw: bytes) -> None:
    """Raise MessageTooLarge or MessageRefused when the inbox must not take
    the message."""
    check_rules(raw, list(inbox.sender_allowlist), inbox.require_auth_results)


async def accept_message(
    db: AsyncSession,
    policy: AccessPolicy,
    principal: Principal,
    *,
    inbox: Inbox,
    raw: bytes,
    received_at: datetime,
) -> StoredRaw:
    """Check the message against the inbox's rules and store it. Does not
    commit; raises MessageTooLarge or MessageRefused."""
    # The rules are read here: the ORM object stays on the event loop.
    allowlist = list(inbox.sender_allowlist)
    await asyncio.to_thread(check_rules, raw, allowlist, inbox.require_auth_results)
    return await store_raw(
        db, policy, principal, inbox_id=inbox.id, raw=raw, received_at=received_at
    )
