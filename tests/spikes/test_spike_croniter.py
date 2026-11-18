"""Spike 6: croniter with zoneinfo across the Europe/Lisbon DST changes.

Lisbon moves from WET (UTC+0) to WEST (UTC+1) at 01:00 local on 28 March 2027
and back at 02:00 local on 31 October 2027. A job keeps its local wall time
across both changes; an hourly job keeps firing once per real hour through the
spring gap. Times inside the gap and the repeated hour are reported as croniter
gives them: the schedule library of phase C3-B applies its own DST policy there.
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


def test_gap_and_repeated_hour_are_reported(report: Callable[..., None]) -> None:
    # 01:30 does not exist on 28 March and exists twice on 31 October.
    spring = datetime(2027, 3, 27, tzinfo=LISBON)
    autumn = datetime(2027, 10, 30, tzinfo=LISBON)
    observed = {
        "spring_0130": next_fires("30 1 * * *", spring, 3),
        "autumn_0130": next_fires("30 1 * * *", autumn, 3),
        "autumn_hourly": next_fires("0 * * * *", autumn.replace(hour=23, minute=30), 4),
    }
    for fires in observed.values():
        instants = [fire.astimezone(UTC) for fire in fires]
        assert instants == sorted(set(instants))
    report(
        "croniter-dst",
        version=version("croniter"),
        **{name: "|".join(local(fires)) for name, fires in observed.items()},
    )
