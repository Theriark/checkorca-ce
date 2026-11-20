"""A schedule suggested from a job's results (Unmatched, phase C5).

The runs of a job that reports every night finish at about the same local
time. The suggestion is a daily schedule at the median of those times, in the
time zone asked for, rounded down to STEP_MINUTES:

- basis: the time each run is read at: finished when at least half of the
  runs (and at least the minimum) give finished_at, else started when as
  many give started_at, else received (every result has it);
- times are local wall-clock times, so runs at 23:00 in Lisbon stay 23:00
  across both DST changes;
- the median is taken around the clock: runs at 23:50 and 00:10 give 00:00,
  not noon. The largest gap between the sorted times is where the day is cut.

Pure code; the API loads the results (app/api/v1/unmatched.py).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal
from zoneinfo import ZoneInfo

Basis = Literal["finished", "started", "received"]

# suggest-schedule needs this many runs; create-job without a schedule takes
# what there is.
MIN_RESULTS: Final = 3
STEP_MINUTES: Final = 5
DAY_MINUTES: Final = 24 * 60


class TooFewResults(ValueError):
    """Fewer runs than the suggestion needs."""


@dataclass(frozen=True, slots=True)
class RunTimes:
    """The times of one result."""

    received_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Suggestion:
    """A daily schedule: expr is one local time HH:MM in timezone. results is
    how many runs the median was taken of."""

    kind: Literal["daily"]
    expr: str
    timezone: str
    basis: Basis
    results: int


def _basis(runs: Sequence[RunTimes], minimum: int) -> tuple[Basis, list[datetime]]:
    """finished or started when at least half of the runs, and at least
    minimum, give that time; else received."""
    needed = max(minimum, (len(runs) + 1) // 2, 1)
    finished = [run.finished_at for run in runs if run.finished_at is not None]
    if len(finished) >= needed:
        return "finished", finished
    started = [run.started_at for run in runs if run.started_at is not None]
    if len(started) >= needed:
        return "started", started
    return "received", [run.received_at for run in runs]


def circular_median(minutes: Sequence[int]) -> int:
    """The median of minutes of the day (0 to 1439), cut where the clock
    leaves the largest gap; the lower median of an even count."""
    ordered = sorted(minute % DAY_MINUTES for minute in minutes)
    if not ordered:
        raise TooFewResults("no times")
    # The gap after each time, the last one wrapping to the first.
    gaps = [
        (ordered[(index + 1) % len(ordered)] - minute) % DAY_MINUTES
        for index, minute in enumerate(ordered)
    ]
    start = (max(range(len(gaps)), key=lambda index: gaps[index]) + 1) % len(gaps)
    unwrapped = [
        minute + (DAY_MINUTES if index < start else 0)
        for index, minute in enumerate(ordered)
    ]
    unwrapped = unwrapped[start:] + unwrapped[:start]
    return unwrapped[(len(unwrapped) - 1) // 2] % DAY_MINUTES


def suggest_daily(
    runs: Sequence[RunTimes],
    zone: ZoneInfo,
    *,
    minimum: int = MIN_RESULTS,
) -> Suggestion:
    """The daily schedule the runs suggest; TooFewResults below minimum."""
    needed = max(minimum, 1)
    if len(runs) < needed:
        raise TooFewResults(f"at least {needed} results are needed")
    basis, times = _basis(runs, needed)
    local = [time.astimezone(zone) for time in times]
    median = circular_median([moment.hour * 60 + moment.minute for moment in local])
    rounded = median - median % STEP_MINUTES
    return Suggestion(
        kind="daily",
        expr=f"{rounded // 60:02d}:{rounded % 60:02d}",
        timezone=zone.key,
        basis=basis,
        results=len(times),
    )
