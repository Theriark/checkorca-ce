"""What every receiver does with a message for one inbox: check, then store.

The SMTP listener, the IMAP poller, POST ingest/email and the .eml upload all
call accept_message, so the same rules hold on every channel:

1. At most 5 MB (store_raw raises MessageTooLarge).
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
fixed word for logs and answers, never an address.
"""

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

# An RFC 8601 comment: (anything without parentheses).
_COMMENT = re.compile(r"\([^()]*\)")
_DKIM_PASS = re.compile(r"^\s*dkim\s*=\s*pass\b", re.IGNORECASE)
_DKIM_DOMAIN = re.compile(r"\bheader\.[di]\s*=\s*\"?@?([A-Za-z0-9.-]+)", re.IGNORECASE)
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


def dkim_passed(headers: Message, addresses: list[str]) -> bool:
    """The topmost Authentication-Results reports dkim=pass for a domain the
    From addresses belong to (relaxed alignment, RFC 7489 3.1.1)."""
    results = headers.get_all("Authentication-Results", [])
    if not results or not addresses:
        return False
    value = _COMMENT.sub(" ", mime.header_value(results[0]))
    # The first item is the authserv-id; the results follow, one per ";".
    signers = []
    for item in value.split(";")[1:]:
        if _DKIM_PASS.match(item) and (found := _DKIM_DOMAIN.search(item)):
            signers.append(found.group(1))
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


def check_message(inbox: Inbox, raw: bytes) -> None:
    """Raise MessageTooLarge or MessageRefused when the inbox must not take
    the message."""
    if len(raw) > MAX_MESSAGE_BYTES:
        raise MessageTooLarge(f"a message may have at most {MAX_MESSAGE_BYTES} bytes")
    if not inbox.sender_allowlist and not inbox.require_auth_results:
        return
    headers = mime.parse_headers(raw)
    addresses = from_addresses(headers)
    if not sender_allowed(list(inbox.sender_allowlist), addresses):
        raise MessageRefused("sender")
    if inbox.require_auth_results and not dkim_passed(headers, addresses):
        raise MessageRefused("authentication")


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
    check_message(inbox, raw)
    return await store_raw(
        db, policy, principal, inbox_id=inbox.id, raw=raw, received_at=received_at
    )
