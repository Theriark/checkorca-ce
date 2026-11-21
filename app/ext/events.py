"""In-process events and the EventSubscriber seam (rnd-report-2 5.3).

The evaluator (phase C7) raises FlipCreated and OccurrenceChanged; the
notification dispatcher (phase C9) raises NotificationSent. Events are
delivered inside the worker after the transaction that made them has
committed, so a subscriber never sees a change that was rolled back. EE reacts
to state changes through a subscriber (tickets, escalation) without polling
the tables. CE ships no subscriber.

A subscriber that raises or takes longer than SUBSCRIBER_TIMEOUT is logged and
skipped; it never stops the tick or the other subscribers. Fields are those of
the Interfaces chapter (In-process events); frozen in phase C12.
"""

import asyncio
import logging
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Protocol

# Seconds one subscriber may take for one event.
SUBSCRIBER_TIMEOUT: Final = 10.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class FlipCreated:
    """A job changed state; the flip row exists (table flip)."""

    flip_id: uuid.UUID
    job_id: uuid.UUID
    client_id: uuid.UUID
    from_state: str
    to_state: str
    reason: str
    at: datetime


@dataclass(frozen=True, slots=True)
class OccurrenceChanged:
    """An occurrence was written with a new state. old_state is None for a new
    occurrence; new_state is None when the evaluator removed an open one (the
    job was paused or its schedule changed)."""

    job_id: uuid.UUID
    scheduled_for: datetime
    old_state: str | None
    new_state: str | None
    at: datetime


@dataclass(frozen=True, slots=True)
class NotificationSent:
    """A notification for a flip went to a channel (raised from phase C9)."""

    notification_id: uuid.UUID
    flip_id: uuid.UUID
    channel_id: uuid.UUID
    status: str


type Event = FlipCreated | OccurrenceChanged | NotificationSent


class EventSubscriber(Protocol):
    """Receives every event after the commit that made it; name is for logs."""

    name: str

    async def handle(self, event: Event) -> None:
        """React to one event. Raising is logged and does not stop the worker."""
        ...


async def deliver(
    subscribers: Sequence[EventSubscriber], events: Iterable[Event]
) -> int:
    """Give each event to each subscriber in order; the number of failures.

    An error or a timeout of one subscriber is logged (with the subscriber's
    name and the event type, never the event's content) and the delivery goes
    on with the next subscriber.
    """
    failures = 0
    if not subscribers:
        return failures
    for event in events:
        for subscriber in subscribers:
            name = getattr(subscriber, "name", type(subscriber).__name__)
            try:
                async with asyncio.timeout(SUBSCRIBER_TIMEOUT):
                    await subscriber.handle(event)
            except Exception as error:
                failures += 1
                logger.error(
                    "event subscriber %s failed on %s",
                    name,
                    type(event).__name__,
                    exc_info=error,
                )
    return failures
