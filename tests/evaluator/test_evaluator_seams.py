"""The C7 extension seams: SuppressionProvider and EventSubscriber (app/ext)."""

import asyncio
import logging
import uuid
from datetime import UTC, datetime

import pytest

from app.ext import events
from app.ext.events import (
    Event,
    FlipCreated,
    NotificationSent,
    OccurrenceChanged,
    deliver,
)
from app.ext.suppression import MaintenanceTarget, NoSuppression

AT = datetime(2027, 1, 5, 7, 30, tzinfo=UTC)
JOB = uuid.uuid4()


async def test_ce_suppresses_nothing() -> None:
    target = MaintenanceTarget(job_id=JOB, client_id=uuid.uuid4())
    assert await NoSuppression().maintenance([target], AT, AT) == {}


async def test_without_subscribers_nothing_is_delivered() -> None:
    assert await deliver((), [OccurrenceChanged(JOB, AT, None, "pending", AT)]) == 0


async def test_every_subscriber_gets_every_event_in_order(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    got: list[tuple[str, Event]] = []

    class Recorder:
        def __init__(self, name: str) -> None:
            self.name = name

        async def handle(self, event: Event) -> None:
            got.append((self.name, event))

    class Slow:
        name = "slow"

        async def handle(self, event: Event) -> None:
            await asyncio.sleep(60)

    changed = OccurrenceChanged(JOB, AT, "overdue", "missed", AT)
    flipped = FlipCreated(uuid.uuid4(), JOB, uuid.uuid4(), "unknown", "missed", "x", AT)
    sent = NotificationSent(uuid.uuid4(), flipped.flip_id, uuid.uuid4(), "sent")
    subscribers = (Recorder("first"), Slow(), Recorder("second"))
    monkeypatch.setattr(events, "SUBSCRIBER_TIMEOUT", 0.01)
    with caplog.at_level(logging.ERROR, logger="app.ext.events"):
        failures = await deliver(subscribers, [changed, flipped, sent])
    # The slow subscriber times out on each event; the others get all three.
    assert failures == 3
    assert got == [
        ("first", changed),
        ("second", changed),
        ("first", flipped),
        ("second", flipped),
        ("first", sent),
        ("second", sent),
    ]
    assert "event subscriber slow failed on FlipCreated" in caplog.text
