"""Spike 6: croniter with zoneinfo across the Europe/Lisbon DST changes.

Lisbon moves from WET (UTC+0) to WEST (UTC+1) at 01:00 local on 28 March 2027
and back at 02:00 local on 31 October 2027. A job keeps its local wall time
across both changes and an hourly job fires once per real hour through both.
A time inside the spring gap fires once, at the end of the gap; a time inside
the repeated autumn hour fires twice. These two cases are pinned as croniter
7.0.0 behaves, so an upgrade that changes them fails here (docs/licences.md,
legal L-2); the schedule library of phase C3-B applies its DST policy on top.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from importlib.metadata import version
from zoneinfo import ZoneInfo

from croniter import croniter

LISBON = ZoneInfo("Europe/Lisbon")


def next_fires(expression: str, start: datetime, count: int) -> list[datetime]:
    schedule = croniter(expression, start)
    return [schedule.get_next(datetime) for _ in range(count)]


def utc(fires: list[datetime]) -> list[str]:
    return [fire.astimezone(UTC).strftime("%m-%d %H:%MZ") for fire in fires]


def local(fires: list[datetime]) -> list[str]:
    return [fire.astimezone(LISBON).strftime("%m-%d %H:%M %Z") for fire in fires]


def test_daily_job_keeps_its_wall_time_across_the_spring_change() -> None:
    fires = next_fires("0 23 * * *", datetime(2027, 3, 26, 12, tzinfo=LISBON), 4)
    assert local(fires) == [
        "03-26 23:00 WET",
        "03-27 23:00 WET",
        "03-28 23:00 WEST",
        "03-29 23:00 WEST",
    ]
    assert utc(fires) == [
        "03-26 23:00Z",
        "03-27 23:00Z",
        "03-28 22:00Z",
        "03-29 22:00Z",
    ]


def test_daily_job_keeps_its_wall_time_across_the_autumn_change() -> None:
    fires = next_fires("0 23 * * *", datetime(2027, 10, 29, 12, tzinfo=LISBON), 4)
    assert local(fires) == [
        "10-29 23:00 WEST",
        "10-30 23:00 WEST",
        "10-31 23:00 WET",
        "11-01 23:00 WET",
    ]
    assert utc(fires) == [
        "10-29 22:00Z",
        "10-30 22:00Z",
        "10-31 23:00Z",
        "11-01 23:00Z",
    ]


def test_hourly_job_fires_once_per_real_hour_through_the_spring_gap() -> None:
    start = datetime(2027, 3, 27, 23, 30, tzinfo=LISBON)
    fires = next_fires("0 * * * *", start, 4)
    assert utc(fires) == [
        "03-28 00:00Z",
        "03-28 01:00Z",
        "03-28 02:00Z",
        "03-28 03:00Z",
    ]
    assert local(fires) == [
        "03-28 00:00 WET",
        "03-28 02:00 WEST",
        "03-28 03:00 WEST",
        "03-28 04:00 WEST",
    ]


def test_time_in_the_spring_gap_fires_once_at_the_end_of_the_gap() -> None:
    # 01:30 does not exist on 28 March: croniter fires at 02:00 WEST instead.
    fires = next_fires("30 1 * * *", datetime(2027, 3, 27, tzinfo=LISBON), 3)
    assert local(fires) == [
        "03-27 01:30 WET",
        "03-28 02:00 WEST",
        "03-29 01:30 WEST",
    ]
    assert utc(fires) == ["03-27 01:30Z", "03-28 01:00Z", "03-29 00:30Z"]


def test_time_in_the_repeated_hour_fires_twice() -> None:
    # 01:30 exists twice on 31 October and croniter fires at both. The schedule
    # library of phase C3-B keeps only the first (docs/spikes.md).
    fires = next_fires("30 1 * * *", datetime(2027, 10, 30, tzinfo=LISBON), 3)
    assert local(fires) == [
        "10-30 01:30 WEST",
        "10-31 01:30 WEST",
        "10-31 01:30 WET",
    ]
    assert utc(fires) == ["10-30 00:30Z", "10-31 00:30Z", "10-31 01:30Z"]


def test_hourly_job_fires_once_per_real_hour_through_the_repeated_hour(
    report: Callable[..., None],
) -> None:
    start = datetime(2027, 10, 30, 23, 30, tzinfo=LISBON)
    fires = next_fires("0 * * * *", start, 4)
    assert utc(fires) == [
        "10-30 23:00Z",
        "10-31 00:00Z",
        "10-31 01:00Z",
        "10-31 02:00Z",
    ]
    assert local(fires) == [
        "10-31 00:00 WEST",
        "10-31 01:00 WEST",
        "10-31 01:00 WET",
        "10-31 02:00 WET",
    ]
    report("croniter-dst", version=version("croniter"), zone="Europe/Lisbon")
