"""ScheduleSpec: what a job's schedule says, checked once when it is parsed.

Three kinds (Interfaces chapter, rnd-report-2 5.4):

- cron: five fields (minute, hour, day of month, month, day of week) or one of
  the macros @hourly, @daily, @midnight, @weekly, @monthly, @yearly, @annually;
  read in the job's time zone.
- daily: one or more local times "HH:MM" separated by commas, for example
  "23:00" or "06:00, 18:00".
- interval: a fixed amount of elapsed time such as "30m", "6h", "1d" or
  "1h30m", counted from the anchor (the job's creation time). Clocks changing
  for daylight saving do not move it.

parse_spec raises ScheduleError with the field to blame and a message a user
can read; the API sends both as a field problem.
"""

import functools
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal, cast
from zoneinfo import ZoneInfo, available_timezones

from app.schedule import _cron

ScheduleKind = Literal["cron", "interval", "daily"]
SCHEDULE_KINDS: Final[tuple[ScheduleKind, ...]] = ("cron", "interval", "daily")
ScheduleField = Literal["schedule_kind", "schedule_expr", "timezone", "anchor"]

MAX_EXPR_LENGTH: Final = 200
MAX_TIMEZONE_LENGTH: Final = 64
MAX_DAILY_TIMES: Final = 48
MIN_INTERVAL: Final = timedelta(minutes=1)
MAX_INTERVAL: Final = timedelta(days=366)

_DAILY_TIME = re.compile(r"([01]?[0-9]|2[0-3]):([0-5][0-9])")
_INTERVAL = re.compile(r"(?:(\d{1,4})d)?(?:(\d{1,5})h)?(?:(\d{1,6})m)?")


class ScheduleError(ValueError):
    """A schedule that cannot be used; field names the input to correct."""

    def __init__(self, field: ScheduleField, message: str) -> None:
        super().__init__(message)
        self.field: ScheduleField = field
        self.message = message


@dataclass(frozen=True, slots=True)
class ScheduleSpec:
    """A checked schedule. Build it with parse_spec, never directly.

    expr is the normalised expression: a five-field cron line, sorted unique
    "HH:MM" times, or the interval as written (lower case, no spaces). anchor
    is set for interval schedules only.
    """

    kind: ScheduleKind
    expr: str
    timezone: str
    anchor: datetime | None = None

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def daily_times(self) -> tuple[tuple[int, int], ...]:
        """The (hour, minute) pairs of a daily schedule."""
        pairs: list[tuple[int, int]] = []
        for item in self.expr.split(","):
            hour, minute = item.split(":")
            pairs.append((int(hour), int(minute)))
        return tuple(pairs)

    @property
    def interval(self) -> timedelta:
        """The step of an interval schedule."""
        return _interval_step(self.expr)


@functools.cache
def _zone_names() -> frozenset[str]:
    return frozenset(available_timezones())


def check_timezone(name: str) -> str:
    """The IANA zone name, checked; ScheduleError for anything else."""
    zone = name.strip()
    if not zone or len(zone) > MAX_TIMEZONE_LENGTH or zone not in _zone_names():
        raise ScheduleError(
            "timezone", "Use an IANA time zone name such as Europe/Lisbon."
        )
    return zone


def _interval_step(expr: str) -> timedelta:
    match = _INTERVAL.fullmatch(expr)
    if match is None or not any(match.groups()):
        raise ScheduleError(
            "schedule_expr",
            "Write an interval as a number with d, h or m, for example 30m, 6h "
            "or 1h30m.",
        )
    days, hours, minutes = (int(part or 0) for part in match.groups())
    return timedelta(days=days, hours=hours, minutes=minutes)


def _parse_interval(expr: str) -> str:
    text = "".join(expr.split()).lower()
    step = _interval_step(text)
    if not MIN_INTERVAL <= step <= MAX_INTERVAL:
        raise ScheduleError(
            "schedule_expr", "An interval must be between 1 minute and 366 days."
        )
    return text


def _parse_daily(expr: str) -> str:
    times: set[tuple[int, int]] = set()
    for item in expr.split(","):
        match = _DAILY_TIME.fullmatch(item.strip())
        if match is None:
            raise ScheduleError(
                "schedule_expr",
                "Write daily times as HH:MM separated by commas, for example "
                "06:00, 18:00.",
            )
        times.add((int(match.group(1)), int(match.group(2))))
    if len(times) > MAX_DAILY_TIMES:
        raise ScheduleError(
            "schedule_expr", f"A daily schedule has at most {MAX_DAILY_TIMES} times."
        )
    return ",".join(f"{hour:02d}:{minute:02d}" for hour, minute in sorted(times))


def parse_spec(
    kind: str, expr: str, timezone: str, anchor: datetime | None = None
) -> ScheduleSpec:
    """Check a schedule and return it in its normalised form.

    anchor is the start of an interval schedule (the job's creation time); the
    other kinds ignore it.
    """
    if kind not in SCHEDULE_KINDS:
        raise ScheduleError("schedule_kind", "Choose cron, interval or daily.")
    checked_kind = cast(ScheduleKind, kind)
    zone = check_timezone(timezone)
    text = expr.strip()
    if not text:
        raise ScheduleError("schedule_expr", "The schedule expression is empty.")
    if len(text) > MAX_EXPR_LENGTH:
        raise ScheduleError(
            "schedule_expr",
            f"The schedule expression is longer than {MAX_EXPR_LENGTH} characters.",
        )
    if checked_kind == "cron":
        try:
            normalised = _cron.normalise(text)
        except _cron.CronSyntaxError as error:
            raise ScheduleError("schedule_expr", str(error)) from None
        return ScheduleSpec(kind="cron", expr=normalised, timezone=zone)
    if checked_kind == "daily":
        return ScheduleSpec(kind="daily", expr=_parse_daily(text), timezone=zone)
    normalised = _parse_interval(text)
    if anchor is None or anchor.utcoffset() is None:
        raise ScheduleError(
            "anchor", "An interval schedule needs an anchor time with a time zone."
        )
    return ScheduleSpec(kind="interval", expr=normalised, timezone=zone, anchor=anchor)
