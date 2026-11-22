"""The ChannelKind and EscalationPolicy seams (rnd-report-2 5.3): how a
notification is delivered, and to which channels when.

A ChannelKind is one way to deliver: CE ships email (app/notify/email.py);
phase C9-I adds slack, teams and webhook to the registry
(app/notify/registry.py) without a schema change, and EE may add more. A kind
checks its settings (config, never a secret), names the settings that decide
where its secret goes, and sends a Message. Sending raises DeliveryError with
one readable sentence; the dispatcher stores that sentence, so it must never
contain the secret. An HTTP kind calls check_target (app/security/ssrf.py)
before every request, with the Outbound rules it is given.

The EscalationPolicy decides, for a flip and the channels whose rules match
it, which channel hears about it after how long. CE ships AllAtOnce: every
matching channel at once. EE can escalate (a second channel after 30
minutes). Frozen in phase C12.
"""

import uuid
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Protocol

from app.ext.events import FlipCreated


class ChannelConfigError(ValueError):
    """A channel setting is unusable: field is the config key ("" for the
    whole config or "secret"), the text says why."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


class DeliveryError(Exception):
    """A delivery failed; detail is one readable sentence without secrets."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True, slots=True)
class FlipFacts:
    """What a notification about a flip tells: the job, its client and the
    change (the Interfaces chapter, Notifications)."""

    flip_id: uuid.UUID
    job_id: uuid.UUID
    job: str
    client_id: uuid.UUID
    client: str
    from_state: str
    to_state: str
    reason: str
    at: datetime
    scheduled_for: datetime | None
    url: str


@dataclass(frozen=True, slots=True)
class Message:
    """One notification ready to send.

    event is failing, missed, warning, recovered, reminder, digest or test.
    subject and text are plain text; html is set for the digest. flip is set
    for the events about a flip, digest_day for the digest; url opens the
    site (the job page or the Morning check).
    """

    event: str
    subject: str
    text: str
    url: str
    html: str | None = None
    flip: FlipFacts | None = None
    digest_day: date | None = None


@dataclass(frozen=True, slots=True)
class Outbound:
    """The SSRF rules an HTTP kind passes to check_target."""

    allow_private: bool = False
    allowed_hosts: frozenset[str] = field(default_factory=frozenset)


class ChannelKind(Protocol):
    """One way to deliver notifications."""

    # The stored kind: email, slack, teams or webhook.
    name: str
    # Shown next to the secret field (Relay password, Webhook URL).
    secret_label: str
    # Config keys that decide where the secret goes: changing one of them
    # needs the secret again, so a stored secret never follows a new target.
    secret_targets: Collection[str]

    def check_config(
        self, config: Mapping[str, Any], *, has_secret: bool
    ) -> dict[str, Any]:
        """The config in its stored form; ChannelConfigError when unusable.
        has_secret says whether a secret is stored or sent with it."""
        ...

    async def send(
        self,
        config: Mapping[str, Any],
        secret: str | None,
        message: Message,
        outbound: Outbound,
    ) -> None:
        """Deliver the message; DeliveryError when it did not arrive."""
        ...


@dataclass(frozen=True, slots=True)
class EscalationStep:
    """Notify channel_id after delay (zero: at once)."""

    channel_id: uuid.UUID
    delay: timedelta = timedelta(0)


class EscalationPolicy(Protocol):
    """Which channels hear about a flip, and when."""

    def plan(
        self, flip: FlipCreated, event: str, channel_ids: Sequence[uuid.UUID]
    ) -> Sequence[EscalationStep]:
        """Steps for the channels whose rules match the flip's event (failing,
        missed, warning or recovered); a channel left out is not notified."""
        ...


class AllAtOnce:
    """CE: every matching channel at once."""

    def plan(
        self, flip: FlipCreated, event: str, channel_ids: Sequence[uuid.UUID]
    ) -> Sequence[EscalationStep]:
        return [EscalationStep(channel_id) for channel_id in channel_ids]
