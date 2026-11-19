"""When a job should run: occurrences in a window, the next n, the deadline.

Every function is pure: same input, same answer, no clock and no I/O. Times
going in must be time zone aware; times coming out are UTC, sorted and unique.
"""

from bisect import insort
from collections.abc import Iterable, Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from app.schedule import _cron, _wall
from app.schedule.spec import ScheduleSpec

# Wall times are listed this far beyond the window on both sides, then cut to
# the window as instants. It must exceed the largest jump of a zone's clocks
# (24 hours in the tz database, Samoa 2011).
_PADDING: Final = timedelta(hours=26)
# next_n reads the zone's offsets at this step to bound the wall times it walks.
# Clocks never change twice within it, so the bound is at most one step off.
_PROBE_STEP: Final = timedelta(hours=1)
_PROBES: Final = range(int(_PADDING / _PROBE_STEP) + 1)
_MINUTE: Final = timedelta(minutes=1)
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


def _fires(
    spec: ScheduleSpec, first: datetime, last: datetime
) -> Iterator[tuple[datetime, list[datetime]]]:
    """Each wall time of a cron or daily spec in [first, last], oldest first,
    with the instants it fires at. Both bounds are naive wall times."""
    zone = spec.zone
    if spec.kind == "cron":
        keep_repeat = _cron.has_wildcard_hour(spec.expr)
        # croniter lists the times after its start; cron times are whole minutes.
        for wall in _cron.wall_times(spec.expr, first - _MINUTE, last):
            if wall >= first:
                yield wall, _wall.instants(wall, zone, keep_repeat=keep_repeat)
        return
    times = sorted(spec.daily_times)
    current: date = first.date()
    while current <= last.date():
        for hour, minute in times:
            wall = datetime(current.year, current.month, current.day, hour, minute)
            if first <= wall <= last:
                yield wall, _wall.instants(wall, zone, keep_repeat=False)
        current += timedelta(days=1)


def _wall_instants(
    spec: ScheduleSpec, start: datetime, end: datetime
) -> list[datetime]:
    zone = spec.zone
    first = _wall.to_wall(start, zone) - _PADDING
    last = _wall.to_wall(end, zone) + _PADDING
    moments = (moment for _, found in _fires(spec, first, last) for moment in found)
    return _within(moments, start, end)


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


def _next_interval_instants(
    spec: ScheduleSpec, begin: datetime, end: datetime, n: int
) -> list[datetime]:
    """The first n instants of an interval spec in [begin, end), by arithmetic."""
    if spec.anchor is None:
        raise ValueError("an interval schedule needs its anchor")
    anchor = spec.anchor.astimezone(UTC)
    step = spec.interval
    index = max(1, -((anchor - begin) // step))
    moments = (anchor + step * (index + offset) for offset in range(n))
    return [moment for moment in moments if moment < end]


def occurrences(spec: ScheduleSpec, start: datetime, end: datetime) -> list[datetime]:
    """Every scheduled time t with start <= t < end, in UTC, oldest first."""
    start = _aware(start, "start")
    end = _aware(end, "end")
    if end <= start:
        return []
    if spec.kind == "interval":
        return _interval_instants(spec, start, end)
    return _wall_instants(spec, start, end)


def _lowest_wall_from(moment: datetime, zone: ZoneInfo) -> datetime:
    """A wall time at or below that of every instant from `moment` on.

    Wall time only falls where clocks go back, by at most _PADDING; after
    _PADDING it is above the wall time of `moment` again.
    """
    walls = (_wall.to_wall(moment + _PROBE_STEP * step, zone) for step in _PROBES)
    return min(walls) - _PROBE_STEP


def _highest_wall_before(moment: datetime, zone: ZoneInfo) -> datetime:
    """A wall time at or above that of every instant before `moment`."""
    walls = (_wall.to_wall(moment - _PROBE_STEP * step, zone) for step in _PROBES)
    return max(walls) + _PROBE_STEP


def _next_wall_instants(
    spec: ScheduleSpec, begin: datetime, end: datetime, n: int
) -> list[datetime]:
    """The first n instants in [begin, end), walking wall times in order.

    Instants do not follow wall order near a clock change, so the walk goes on
    until a wall time lies above the wall time of every instant before the n-th
    found; any later wall time fires at or after the n-th. A dense schedule
    costs about n times plus two hours of wall times, whatever the window.
    """
    zone = spec.zone
    first = _lowest_wall_from(begin, zone)
    last = _wall.to_wall(end, zone) + _PADDING
    found: list[datetime] = []
    settled: tuple[datetime, datetime] | None = None
    for wall, moments in _fires(spec, first, last):
        if len(found) == n:
            if settled is None or settled[0] != found[-1]:
                settled = (found[-1], _highest_wall_before(found[-1], zone))
            if wall > settled[1]:
                break
        for moment in moments:
            if begin <= moment < end and moment not in found:
                insort(found, moment)
                del found[n:]
    return found


def next_n(spec: ScheduleSpec, after: datetime, n: int) -> list[datetime]:
    """The first n scheduled times strictly after `after`.

    Fewer than n (possibly none) when the schedule fires less often within
    NEXT_HORIZON, for example 29 February or a date that never exists. The
    work grows with n, not with the window, so a schedule that fires every
    minute of a few months costs as little as a daily one.
    """
    after = _aware(after, "after")
    if n <= 0:
        return []
    begin = after + timedelta(microseconds=1)
    end = after + NEXT_HORIZON
    if spec.kind == "interval":
        return _next_interval_instants(spec, begin, end, n)
    return _next_wall_instants(spec, begin, end, n)


def deadline(
    scheduled_for: datetime, max_runtime_minutes: int, grace_minutes: int
) -> datetime:
    """When an occurrence without a final result turns overdue: t + R + G."""
    if max_runtime_minutes < 0 or grace_minutes < 0:
        raise ValueError("runtime and grace cannot be negative")
    moment = _aware(scheduled_for, "scheduled_for")
    return moment + timedelta(minutes=max_runtime_minutes + grace_minutes)
