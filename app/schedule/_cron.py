"""The only module that imports croniter (pinned, MIT; docs/licences.md L-2).

croniter is used for one thing: listing the local wall-clock times that match a
five-field cron expression. It is fed a naive wall time dressed as UTC, so it
never sees a time zone and no daylight-saving rule of the library applies.
Turning wall times into real instants (the DST policy) is app/schedule/_wall.py.
Swapping croniter for an own parser (the planned fallback) changes this module
only.
"""

import importlib
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, Final, cast

# croniter ships no type information; the class is used through Any here only.
_croniter_module = importlib.import_module("croniter")
_CRONITER: Any = _croniter_module.croniter
_BAD_DATE: type[Exception] = _croniter_module.CroniterBadDateError

# How far croniter searches for the next match before it gives up. Eight years
# is the longest gap of a real expression (29 February across 2100).
MAX_YEARS_BETWEEN_MATCHES: Final = 10

MACROS: Final = {
    "@yearly": "0 0 1 1 *",
    "@annually": "0 0 1 1 *",
    "@monthly": "0 0 1 * *",
    "@weekly": "0 0 * * 0",
    "@daily": "0 0 * * *",
    "@midnight": "0 0 * * *",
    "@hourly": "0 * * * *",
}
_FIELD = re.compile(r"[0-9A-Za-z*/,?#-]+")
# Hashed (H) and random (R) values of croniter: a schedule must be readable.
_HASHED_OR_RANDOM = re.compile(r"[HR](\(.*\))?(/\d+)?", re.IGNORECASE)
_WILDCARD_HOUR = re.compile(r"\*(/\d+)?")
_CHECK_START = datetime(2000, 1, 1, tzinfo=UTC)


class CronSyntaxError(ValueError):
    """An expression croniter (or the rules here) refuses; the text is for users."""


def normalise(expr: str) -> str:
    """The five fields separated by single spaces; CronSyntaxError otherwise."""
    text = expr.strip()
    if text.startswith("@"):
        macro = MACROS.get(text.lower())
        if macro is None:
            raise CronSyntaxError(
                "Unknown cron macro; use @hourly, @daily, @weekly, @monthly or "
                "@yearly."
            )
        return macro
    fields = text.split()
    if len(fields) != 5:
        raise CronSyntaxError(
            "A cron expression has five fields: minute, hour, day of month, "
            "month and day of week."
        )
    for field in fields:
        if not _FIELD.fullmatch(field) or any(
            _HASHED_OR_RANDOM.fullmatch(item) for item in field.split(",")
        ):
            raise CronSyntaxError(
                "Not a valid cron expression: check each of the five fields."
            )
    line = " ".join(fields)
    try:
        _CRONITER(line, _CHECK_START, max_years_between_matches=1)
    except (ArithmeticError, LookupError, TypeError, ValueError):
        raise CronSyntaxError(
            "Not a valid cron expression: check each of the five fields."
        ) from None
    return line


def has_wildcard_hour(expr: str) -> bool:
    """True when the hour field of a normalised expression is * or */n.

    Such a schedule fires in every real hour, so both instances of a repeated
    local hour are kept (docs/spikes.md, finding for C3-B).
    """
    return _WILDCARD_HOUR.fullmatch(expr.split()[1]) is not None


def wall_times(expr: str, after: datetime, until: datetime) -> Iterator[datetime]:
    """Naive local wall times that match expr, after `after`, up to `until`.

    Both bounds are naive. The iteration ends early when croniter finds no
    match within MAX_YEARS_BETWEEN_MATCHES years.
    """
    schedule = _CRONITER(
        expr,
        after.replace(tzinfo=UTC),
        max_years_between_matches=MAX_YEARS_BETWEEN_MATCHES,
    )
    while True:
        try:
            fire = cast(datetime, schedule.get_next(datetime))
        except _BAD_DATE:
            return
        wall = fire.replace(tzinfo=None)
        if wall > until:
            return
        yield wall
