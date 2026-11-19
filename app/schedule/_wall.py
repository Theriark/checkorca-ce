"""Local wall time to real instants: the DST policy of rnd-report-2 5.5.

- A wall time that exists once is that instant.
- A wall time inside a spring-forward gap does not exist; it fires once, at the
  first valid instant after the gap (01:30 on a Lisbon spring day becomes
  02:00 WEST).
- A wall time inside a repeated autumn hour exists twice; it fires once, at the
  first of the two. Schedules that fire in every real hour (cron with a * or
  */n hour) keep both, because each is a real hour (docs/spikes.md).

The rule depends only on the wall time and the zone, never on earlier fires, so
a restart or a different query window gives the same instants.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def to_wall(instant: datetime, zone: ZoneInfo) -> datetime:
    """The naive local wall time of an aware instant."""
    return instant.astimezone(zone).replace(tzinfo=None)


def _round_trips(candidate: datetime, wall: datetime, zone: ZoneInfo) -> bool:
    return to_wall(candidate, zone) == wall


def _transition(before: datetime, after: datetime, zone: ZoneInfo) -> datetime:
    """The first instant in (before, after] with the offset `after` has.

    Offsets change on whole seconds, so a binary search over seconds finds the
    change in at most a few dozen steps.
    """
    target = after.astimezone(zone).utcoffset()
    low, high = 0, int((after - before).total_seconds())
    while high - low > 1:
        middle = (low + high) // 2
        probe = before + timedelta(seconds=middle)
        if probe.astimezone(zone).utcoffset() == target:
            high = middle
        else:
            low = middle
    return before + timedelta(seconds=high)


def instants(wall: datetime, zone: ZoneInfo, *, keep_repeat: bool) -> list[datetime]:
    """The UTC instants at which a naive wall time fires, oldest first."""
    # fold 0 reads the wall time with the offset before a change, fold 1 with
    # the offset after it; outside a change both give the same instant.
    candidates = sorted(
        {wall.replace(tzinfo=zone, fold=fold).astimezone(UTC) for fold in (0, 1)}
    )
    existing = [moment for moment in candidates if _round_trips(moment, wall, zone)]
    if existing:
        return existing if keep_repeat else existing[:1]
    # A gap: neither offset reaches this wall time. The clocks jumped forward
    # between the two candidates; fire at the jump.
    return [_transition(candidates[0], candidates[-1], zone)]
