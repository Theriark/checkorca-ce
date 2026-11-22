"""The daily digest goes out once per local day at settings.digest_time_local
in settings.digest_timezone, also on the days the clocks change, in
Europe/Lisbon and America/New_York (phase C9-B).

The rule itself (due_digest_day) is walked minute by minute; the dispatcher
is ticked every 20 minutes on PostgreSQL with a fake kind, so nothing leaves
the test.
"""

import dataclasses
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM
from app.db.models import AppSettings, Notification
from app.ext.notifications import Message, Outbound
from app.notify.dispatcher import dispatch_notifications, due_digest_day
from app.notify.registry import KindRegistry
from app.notify.windows import local_moment
from app.repos.notifications import ChannelRepository, ChannelRuleRepository
from app.settings import load_settings
from app.worker.loop import WorkerContext, build_context
from helpers import FakeClock

# The weekends the clocks change in 2027, and digest times that the change
# skips (spring) or repeats (autumn) in that zone.
CHANGES = [
    ("Europe/Lisbon", date(2027, 3, 28), time(1, 30)),
    ("Europe/Lisbon", date(2027, 10, 31), time(1, 30)),
    ("Europe/Lisbon", date(2027, 3, 28), time(7, 30)),
    ("America/New_York", date(2027, 3, 14), time(2, 30)),
    ("America/New_York", date(2027, 11, 7), time(1, 30)),
    ("America/New_York", date(2027, 11, 7), time(7, 30)),
]
IDS = [f"{zone}-{day}-{at:%H%M}" for zone, day, at in CHANGES]


def days_around(day: date) -> list[date]:
    return [day + timedelta(days=offset) for offset in (-1, 0, 1)]


@pytest.mark.parametrize(("zone_name", "change", "digest_time"), CHANGES, ids=IDS)
def test_the_rule_gives_each_local_day_one_digest(
    zone_name: str, change: date, digest_time: time
) -> None:
    zone = ZoneInfo(zone_name)
    days = days_around(change)
    now = local_moment(days[0], time(0, 0), zone)
    end = local_moment(days[-1] + timedelta(days=1), time(0, 0), zone)
    sent: dict[date, datetime] = {}
    while now < end:
        day = due_digest_day(now, zone, digest_time)
        if day is not None and day not in sent:
            sent[day] = now
        now += timedelta(minutes=1)
    assert list(sent) == days
    for day, moment in sent.items():
        assert moment == local_moment(day, digest_time, zone)
        assert moment.astimezone(zone).date() == day


class DigestKind:
    """Registered as email; keeps what it is given."""

    name = "email"
    secret_label = "Relay password"
    secret_targets = frozenset({"host"})

    def __init__(self) -> None:
        self.sent: list[Message] = []

    def check_config(
        self, config: Mapping[str, Any], *, has_secret: bool
    ) -> dict[str, Any]:
        return dict(config)

    async def send(
        self,
        config: Mapping[str, Any],
        secret: str | None,
        message: Message,
        outbound: Outbound,
    ) -> None:
        self.sent.append(message)


@pytest.fixture
def kind() -> DigestKind:
    return DigestKind()


@pytest.fixture
async def context(
    db_engine: AsyncEngine, clock: FakeClock, kind: DigestKind
) -> AsyncIterator[WorkerContext]:
    built = build_context(load_settings(), clock)
    yield dataclasses.replace(built, kinds=KindRegistry([kind]))
    await built.engine.dispose()


async def add_digest_channel(context: WorkerContext, events: list[str]) -> None:
    async with context.sessionmaker() as db:
        channel = await ChannelRepository(db, context.policy).create(
            SYSTEM,
            kind="email",
            label="Morning mail",
            now=context.clock.now(),
            config={"host": "relay.example.com"},
        )
        await ChannelRuleRepository(db, context.policy).create(
            SYSTEM,
            channel_id=channel.id,
            scope="all",
            scope_id=None,
            events=events,
            now=context.clock.now(),
        )
        await db.commit()


@pytest.mark.parametrize(("zone_name", "change", "digest_time"), CHANGES, ids=IDS)
async def test_the_dispatcher_sends_one_digest_per_local_day(
    context: WorkerContext,
    kind: DigestKind,
    db_engine: AsyncEngine,
    clock: FakeClock,
    zone_name: str,
    change: date,
    digest_time: time,
) -> None:
    async with db_engine.begin() as connection:
        await connection.execute(
            update(AppSettings).values(
                digest_timezone=zone_name, digest_time_local=digest_time
            )
        )
    zone = ZoneInfo(zone_name)
    days = days_around(change)
    start = local_moment(days[0], time(0, 0), zone)
    end = local_moment(days[-1] + timedelta(days=1), time(0, 0), zone)
    clock.advance(seconds=(start - clock.now()).total_seconds())
    await add_digest_channel(context, ["digest"])
    # A channel without the digest event gets none.
    await add_digest_channel(context, ["missed"])
    step = timedelta(minutes=20)
    while clock.now() < end:
        await dispatch_notifications(context, clock.now())
        clock.advance(seconds=step.total_seconds())
    query = select(Notification).order_by(Notification.created_at)
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        rows = list((await db.scalars(query)).all())
    assert [row.digest_day for row in rows] == days
    outcomes = {(row.event, row.status, row.flip_id) for row in rows}
    assert outcomes == {("digest", "sent", None)}
    for row in rows:
        assert row.digest_day is not None
        due = local_moment(row.digest_day, digest_time, zone)
        assert timedelta(0) <= row.created_at - due < step
    assert [message.digest_day for message in kind.sent] == days
    first = kind.sent[0]
    assert first.event == "digest" and first.html is not None
    assert first.subject == f"Checkorca-CE morning check {days[0]}: no runs were due"
    assert first.url == "http://localhost:8080/"


async def test_a_digest_channel_added_later_gets_the_day_once(
    context: WorkerContext, kind: DigestKind, clock: FakeClock
) -> None:
    """The fake clock starts at 09:00Z, after the 07:30 Lisbon digest time:
    a new channel gets that day's digest at once, and no second one."""
    assert clock.now() == datetime(2027, 1, 4, 9, tzinfo=UTC)
    await dispatch_notifications(context, clock.now())
    assert kind.sent == []
    await add_digest_channel(context, ["digest", "missed"])
    for _ in range(3):
        await dispatch_notifications(context, clock.now())
        clock.advance(hours=2)
    assert [message.digest_day for message in kind.sent] == [date(2027, 1, 4)]
