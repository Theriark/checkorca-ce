"""The bodies of the webhook, Slack and Teams kinds (phase C9-I), all built
from the same Message.

event_payload is the webhook payload v1 of the Interfaces chapter
(Notifications): event, at, job (id, name, kind), client (id, name), state,
previous_state, reason, occurrence (scheduled_for, deadline), url, product,
schema_version. The digest payload is event digest, date, counts and items
(client, job, state). docs/webhook-payload.schema.json is the published
contract; tests validate every payload against it
(tests/notify/test_webhook_kinds.py).

Slack and Teams get the same facts as a short plain text plus one block or
card. Every name and reason from the database goes through escape_markup, so
user content can never become markup (a job called <b> stays text).
"""

from datetime import UTC, datetime
from typing import Any, Final

from app import PRODUCT_NAME
from app.ext.notifications import Message

# The words of the digest states, the same table as app/notify/digest.py
# keeps for the e-mail body (kept here so the payload builders stay pure).
STATE_WORDS: Final[dict[str, str]] = {
    "missed": "Missed",
    "overdue": "Overdue",
    "failed": "Failed",
    "warning": "Warning",
}

SCHEMA_VERSION: Final = 1
# Slack block and Teams card limits (the docs of both): the header and every
# section text are cut to these, so a long name cannot break the body.
MAX_HEADER: Final = 150
MAX_SECTION: Final = 2800
# Items shown in one Slack or Teams digest body; the rest are counted.
MAX_DIGEST_ITEMS: Final = 10
# The themeColor of a Teams card, from the Brand status tokens; anything
# else (a test, a reminder of a state that is not in the table) is ink.
COLOURS: Final[dict[str, str]] = {
    "failing": "D0202A",
    "missed": "D0202A",
    "reminder": "D0202A",
    "warning": "9A5B00",
    "recovered": "1E7B4F",
}
INK_COLOUR: Final = "121417"


def iso(moment: datetime) -> str:
    """The moment in UTC as the API shows times: YYYY-MM-DDTHH:MM:SSZ."""
    if moment.tzinfo is None:
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def escape_markup(text: str) -> str:
    """The Slack and Teams entities of the three characters both render as
    markup: a hostile name stays text (shown with its entities)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _event_payload(message: Message) -> dict[str, Any]:
    """The payload of a message about a flip, a reminder or a test."""
    payload: dict[str, Any] = {
        "event": message.event,
        "at": None if message.at is None else iso(message.at),
        "url": message.url,
        "product": PRODUCT_NAME,
        "schema_version": SCHEMA_VERSION,
    }
    facts = message.flip
    if facts is None:
        return payload
    occurrence = None
    if facts.scheduled_for is not None:
        occurrence = {
            "scheduled_for": iso(facts.scheduled_for),
            "deadline": None if facts.deadline is None else iso(facts.deadline),
        }
    payload |= {
        "job": {"id": str(facts.job_id), "name": facts.job, "kind": facts.job_kind},
        "client": {"id": str(facts.client_id), "name": facts.client},
        "state": facts.to_state,
        "previous_state": facts.from_state,
        "reason": facts.reason,
        "occurrence": occurrence,
    }
    return payload


def _digest_payload(message: Message) -> dict[str, Any]:
    """The payload of the daily digest: event digest, date, counts, items."""
    digest = message.digest
    if digest is None:
        raise ValueError("a digest message carries its digest")
    return {
        "event": "digest",
        "at": iso(digest.generated_at),
        "url": message.url,
        "product": PRODUCT_NAME,
        "schema_version": SCHEMA_VERSION,
        "date": digest.day.isoformat(),
        "counts": {
            "verified": digest.verified,
            "failed": digest.failed,
            "silent": digest.silent,
            "warning": digest.warning,
        },
        "items": [
            {"client": item.client, "job": item.job, "state": item.state}
            for item in digest.items
        ],
    }


def payload_of(message: Message) -> dict[str, Any]:
    """The webhook payload v1 of the message (docs/webhook-payload.schema.json)."""
    if message.event == "digest":
        return _digest_payload(message)
    return _event_payload(message)


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _left_over(digest: Any) -> int:
    """How many jobs of the digest no card body lists."""
    return len(digest.items) - MAX_DIGEST_ITEMS + digest.more_items


def _slack_sections(message: Message) -> list[dict[str, Any]]:
    """The section blocks of one Slack message, silent first in a digest."""
    facts = message.flip
    if facts is not None:
        lines = [
            f"State: {facts.from_state} to {facts.to_state} at {iso(facts.at)}",
            f"Why: {facts.reason}",
        ]
        if facts.scheduled_for is not None:
            lines.append(f"Run due: {iso(facts.scheduled_for)}")
        return [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": escape_markup("\n".join(lines))},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"<{escape_markup(facts.url)}|Open the job>",
                },
            },
        ]
    digest = message.digest
    if digest is None:
        # The test message: its text, escaped, as one section.
        return [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": escape_markup(message.text)},
            }
        ]
    counts = (
        f"Verified: {digest.verified}, failed: {digest.failed}, "
        f"silent: {digest.silent}, warning: {digest.warning}"
    )
    sections = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": escape_markup(counts)},
        }
    ]
    for item in digest.items[:MAX_DIGEST_ITEMS]:
        line = (
            f"{STATE_WORDS.get(item.state, item.state)}: {item.client} / "
            f"{item.job}, due {iso(item.scheduled_for)}"
        )
        sections.append(
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": escape_markup(line)},
            }
        )
    if _left_over(digest) > 0:
        sections.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"And {_left_over(digest)} more jobs on the Morning check.",
                },
            }
        )
    sections.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"<{escape_markup(digest.url)}|Open the Morning check>",
            },
        }
    )
    return sections


def slack_body(message: Message) -> dict[str, Any]:
    """The body of a Slack incoming webhook: the plain text, plus a header
    block and a few section blocks built from the same facts. The header is
    plain_text, which Slack never renders as markup."""
    return {
        "text": _one_line(message.text),
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": _one_line(message.subject)[:MAX_HEADER],
                },
            },
        ]
        + _slack_sections(message),
    }


def _teams_sections(message: Message) -> list[dict[str, Any]]:
    """The sections of one Teams card: the counts of a digest and the jobs
    that need attention."""
    digest = message.digest
    if digest is None:
        return []
    sections = [
        {
            "text": (
                f"Verified {digest.verified}, failed {digest.failed}, "
                f"silent {digest.silent}, warning {digest.warning}"
            )
        }
    ]
    facts = [
        {
            "name": escape_markup(
                f"{STATE_WORDS.get(item.state, item.state)}: "
                f"{item.client} / {item.job}"
            ),
            "value": escape_markup(f"due {iso(item.scheduled_for)}"),
        }
        for item in digest.items[:MAX_DIGEST_ITEMS]
    ]
    if facts:
        sections.append({"facts": facts})
        if _left_over(digest) > 0:
            sections.append(
                {"text": f"And {_left_over(digest)} more jobs on the Morning check."}
            )
    return sections


def teams_body(message: Message) -> dict[str, Any]:
    """The body of a Teams message card: the subject as title and summary,
    the plain text escaped as text, and the digest counts and items as
    sections."""
    return {
        "@type": "MessageCard",
        "@context": "http://schema.org/extensions",
        "themeColor": COLOURS.get(message.event, INK_COLOUR),
        "summary": _one_line(message.subject)[:MAX_SECTION],
        "title": _one_line(message.subject)[:MAX_SECTION],
        "text": escape_markup(message.text[:MAX_SECTION]),
        "sections": _teams_sections(message),
    }
