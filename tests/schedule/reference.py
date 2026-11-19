"""A slow, obvious second implementation of the schedule rules, for the tests.

It walks every UTC minute of a window, so it never handles a wall time it does
not see: the repeated autumn hour shows up twice by itself and the spring gap
shows up as a jump in wall time. The DST policy (rnd-report-2 5.5,
docs/spikes.md) is applied on top:

- a fixed-hour schedule keeps only the first of the two repeated instances
  (fold 0 after astimezone);
- a wall time that falls in a gap fires once, at the first instant after it.

Cron support is the plain numeric subset: *, */n, a, a-b, a-b/n and lists, in
five fields, with day of month and day of week combined by OR when both are
restricted (as croniter does). No croniter import here.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
MINUTE = timedelta(minutes=1)


def _values(field: str, low: int, high: int) -> set[int]:
    found: set[int] = set()
    for item in field.split(","):
        part, _, step_text = item.partition("/")
        step = int(step_text) if step_text else 1
        if part == "*":
            first, last = low, high
        elif "-" in part:
            first_text, last_text = part.split("-")
            first, last = int(first_text), int(last_text)
        else:
            first = last = int(part)
            if step_text:
                last = high
        found.update(range(first, last + 1, step))
    return found


class Cron:
    """A parsed numeric five-field expression."""

    def __init__(self, expr: str) -> None:
        fields = expr.split()
        assert len(fields) == 5, expr
        self.fields = fields
        sets = [
            _values(field, low, high)
            for field, (low, high) in zip(fields, RANGES, strict=True)
        ]
        self.minutes, self.hours, self.days, self.months, weekdays = sets
        self.weekdays = {day % 7 for day in weekdays}
        # As croniter decides it: a field is restricted when it does not cover
        # every value (so */2 restricts the day of month; Vixie cron differs).
        self.day_restricted = self.days != set(range(1, 32))
        self.weekday_restricted = self.weekdays != set(range(7))
        self.wildcard_hour = fields[1] == "*" or fields[1].startswith("*/")

    def matches(self, wall: datetime) -> bool:
        if wall.minute not in self.minutes or wall.hour not in self.hours:
            return False
        if wall.month not in self.months:
            return False
        day = wall.day in self.days
        weekday = (wall.weekday() + 1) % 7 in self.weekdays
        if self.day_restricted and self.weekday_restricted:
            return day or weekday
        return day and weekday


def _minutes(start: datetime, end: datetime) -> Iterator[datetime]:
    moment = start.astimezone(UTC).replace(second=0, microsecond=0)
    if moment < start:
        moment += MINUTE
    while moment < end:
        yield moment
        moment += MINUTE


def cron_occurrences(
    expr: str, timezone: str, start: datetime, end: datetime
) -> list[datetime]:
    """Instants in [start, end) by a minute-by-minute walk."""
    cron = Cron(expr)
    zone = ZoneInfo(timezone)
    found: set[datetime] = set()
    previous_wall: datetime | None = None
    # One minute before the window, so a gap right at the start is seen.
    for moment in _minutes(start - MINUTE, end):
        local = moment.astimezone(zone)
        wall = local.replace(tzinfo=None)
        if previous_wall is not None and wall - previous_wall > MINUTE:
            skipped = previous_wall + MINUTE
            while skipped < wall:
                if cron.matches(skipped) and moment >= start:
                    found.add(moment)
                skipped += MINUTE
        previous_wall = wall
        if moment < start or not cron.matches(wall):
            continue
        if local.fold == 1 and not cron.wildcard_hour:
            continue
        found.add(moment)
    return sorted(found)


def daily_as_cron(times: str) -> list[str]:
    """A daily schedule as one fixed-hour cron line per time."""
    lines = []
    for item in times.split(","):
        hour, minute = item.strip().split(":")
        lines.append(f"{int(minute)} {int(hour)} * * *")
    return lines


def daily_occurrences(
    times: str, timezone: str, start: datetime, end: datetime
) -> list[datetime]:
    found: set[datetime] = set()
    for line in daily_as_cron(times):
        found.update(cron_occurrences(line, timezone, start, end))
    return sorted(found)
