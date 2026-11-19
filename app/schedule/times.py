"""When a job should run: occurrences in a window, the next n, the deadline.

Every function is pure: same input, same answer, no clock and no I/O. Times
going in must be time zone aware; times coming out are UTC, sorted and unique.
"""

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta
from typing import Final

from app.schedule import _cron, _wall
from app.schedule.spec import ScheduleSpec

# Wall times are listed this far beyond the window on both sides, then cut to
# the window as instants. It must exceed the largest jump of a zone's clocks
# (24 hours in the tz database, Samoa 2011).
_PADDING: Final = timedelta(hours=26)
# The longest window next_n searches before it answers with fewer times.
NEXT_HORIZON: Final = timedelta(days=3660)
# A window that would hold more occurrences than this is refused.
MAX_OCCURRENCES: Final = 100_000


class TooManyOccurrences(ValueError):
    """The window holds more than MAX_OCCURRENCES occurrences."""


def _aware(moment: datetime, name: str) -> datetime:
    if moment.utcoffset() is None:
        raise ValueError(f"{name} must be time zone aware")
    return moment.astimezone(UTC)


def _within(
    moments: Iterable[datetime], start: datetime, end: datetime
) -> list[datetime]:
    found: set[datetime] = set()
    for moment in moments:
        if start <= moment < end:
            found.add(moment)
            if len(found) > MAX_OCCURRENCES:
                raise TooManyOccurrences(
                    f"more than {MAX_OCCURRENCES} occurrences in the window"
                )
    return sorted(found)


def _cron_instants(
    spec: ScheduleSpec, start: datetime, end: datetime
) -> list[datetime]:
    zone = spec.zone
    keep_repeat = _cron.has_wildcard_hour(spec.expr)
    first = _wall.to_wall(start, zone) - _PADDING
    last = _wall.to_wall(end, zone) + _PADDING

    def moments() -> Iterable[datetime]:
        for wall in _cron.wall_times(spec.expr, first, last):
            yield from _wall.instants(wall, zone, keep_repeat=keep_repeat)

    return _within(moments(), start, end)


def _daily_instants(
    spec: ScheduleSpec, start: datetime, end: datetime
) -> list[datetime]:
    zone = spec.zone
    times = spec.daily_times
    day = (_wall.to_wall(start, zone) - _PADDING).date()
    last_day = (_wall.to_wall(end, zone) + _PADDING).date()

    def moments() -> Iterable[datetime]:
        current: date = day
        while current <= last_day:
            for hour, minute in times:
                wall = datetime(current.year, current.month, current.day, hour, minute)
                yield from _wall.instants(wall, zone, keep_repeat=False)
            current += timedelta(days=1)

    return _within(moments(), start, end)


def _interval_instants(
    spec: ScheduleSpec, start: datetime, end: datetime
) -> list[datetime]:
    if spec.anchor is None:
        raise ValueError("an interval schedule needs its anchor")
    anchor = spec.anchor.astimezone(UTC)
    step = spec.interval
    # The first occurrence is one step after the anchor (the job's creation).
    index = max(1, -((anchor - start) // step))
    count = max(0, -((anchor - end) // step) - index)
    if count > MAX_OCCURRENCES:
        raise TooManyOccurrences(
            f"more than {MAX_OCCURRENCES} occurrences in the window"
        )
    moments = (anchor + step * (index + offset) for offset in range(count))
    return _within(moments, start, end)


def occurrences(spec: ScheduleSpec, start: datetime, end: datetime) -> list[datetime]:
    """Every scheduled time t with start <= t < end, in UTC, oldest first."""
    start = _aware(start, "start")
    end = _aware(end, "end")
    if end <= start:
        return []
    if spec.kind == "cron":
        return _cron_instants(spec, start, end)
    if spec.kind == "daily":
        return _daily_instants(spec, start, end)
    return _interval_instants(spec, start, end)


def next_n(spec: ScheduleSpec, after: datetime, n: int) -> list[datetime]:
    """The first n scheduled times strictly after `after`.

    Fewer than n (possibly none) when the schedule fires less often within
    NEXT_HORIZON, for example 29 February or a date that never exists.
    """
    after = _aware(after, "after")
    if n <= 0:
        return []
    if spec.kind == "interval":
        span = spec.interval * (n + 1)
    else:
        span = timedelta(days=2)
    begin = after + timedelta(microseconds=1)
    while True:
        span = min(span, NEXT_HORIZON)
        found = occurrences(spec, begin, after + span)
        if len(found) >= n or span >= NEXT_HORIZON:
            return found[:n]
        span *= 4


def deadline(
    scheduled_for: datetime, max_runtime_minutes: int, grace_minutes: int
) -> datetime:
    """When an occurrence without a final result turns overdue: t + R + G."""
    if max_runtime_minutes < 0 or grace_minutes < 0:
        raise ValueError("runtime and grace cannot be negative")
    moment = _aware(scheduled_for, "scheduled_for")
    return moment + timedelta(minutes=max_runtime_minutes + grace_minutes)
