"""What a notification says (phase C9-B): the message of a flip, a reminder,
the daily digest and a channel test.

The text is plain and short: the client and the job, what changed, why (the
flip's reason) and a link to the job. Times are shown in the digest zone. The
subject holds the client and job names on one line; the e-mail kind makes it
a single header line. Webhook kinds (C9-I) use Message.flip, not the text.
"""

from datetime import date, datetime
from typing import Final
from zoneinfo import ZoneInfo

from app import PRODUCT_NAME
from app.ext.notifications import FlipFacts, Message
from app.ext.reports import RenderedReport

# What the job did, after "Client / Job".
EVENT_PHRASES: Final[dict[str, str]] = {
    "failing": "is failing",
    "missed": "missed its run",
    "warning": "finished with a warning",
    "recovered": "recovered",
}
# A reminder, by the state the job is still in.
REMINDER_PHRASES: Final[dict[str, str]] = {
    "failing": "is still failing after 24 hours",
    "missed": "has still not reported after 24 hours",
}


def local_time(moment: datetime, zone: ZoneInfo) -> str:
    return moment.astimezone(zone).strftime("%Y-%m-%d %H:%M")


def phrase_of(event: str, facts: FlipFacts) -> str:
    if event == "reminder":
        return REMINDER_PHRASES.get(facts.to_state, f"is still {facts.to_state}")
    return EVENT_PHRASES.get(event, f"changed to {facts.to_state}")


def flip_message(event: str, facts: FlipFacts, zone: ZoneInfo) -> Message:
    """The message of a flip (failing, missed, warning, recovered) or of its
    24-hour reminder."""
    headline = f"{facts.client} / {facts.job} {phrase_of(event, facts)}"
    lines = [
        f"{headline}.",
        "",
        f"State: {facts.from_state} to {facts.to_state} at "
        f"{local_time(facts.at, zone)} ({zone.key})",
        f"Why: {facts.reason}",
    ]
    if facts.scheduled_for is not None:
        lines.append(f"Run due: {local_time(facts.scheduled_for, zone)}")
    lines += ["", f"Open the job: {facts.url}", "", f"Sent by {PRODUCT_NAME}."]
    return Message(
        event=event,
        subject=f"{PRODUCT_NAME}: {headline}",
        text="\n".join(lines) + "\n",
        url=facts.url,
        flip=facts,
    )


def digest_message(report: RenderedReport, url: str, day: date) -> Message:
    """The daily digest of day as the ReportRenderer made it."""
    return Message(
        event="digest",
        subject=report.subject,
        text=report.text,
        html=report.html,
        url=url,
        digest_day=day,
    )


def channel_test_message(label: str, url: str, now: datetime) -> Message:
    """The message channels/{id}/test sends."""
    return Message(
        event="test",
        subject=f"{PRODUCT_NAME}: test of the channel {label}",
        text=(
            f"This is a test of the notification channel {label}, sent at "
            f"{now.isoformat(timespec='seconds')}.\n\n"
            "Notifications about your jobs will arrive like this one.\n\n"
            f"Open {PRODUCT_NAME}: {url}\n"
        ),
        url=url,
    )
