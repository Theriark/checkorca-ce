"""Local days and nights in the digest zone (settings.digest_timezone).

The dashboard trend, the day export and the digest count by calendar day in
that zone; the Night Ribbon shows the night from 18:00 to 12:00. Every bound
is a UTC instant. A local time that does not exist (the hour skipped when
summer time starts) is read with the offset before the change, as zoneinfo
does, so a bound always exists and days stay in order.
"""

from datetime import UTC, date, datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo

NIGHT_START: Final = time(18, 0)
NIGHT_END: Final = time(12, 0)


def local_moment(day: date, at: time, zone: ZoneInfo) -> datetime:
    """day at the local time in the zone, as a UTC instant."""
    return datetime.combine(day, at, tzinfo=zone).astimezone(UTC)


def local_date(moment: datetime, zone: ZoneInfo) -> date:
    """The calendar day of the instant in the zone."""
    return moment.astimezone(zone).date()


def day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """[start, end) of the local calendar day (23 or 25 hours across a
    change of the clocks)."""
    return (
        local_moment(day, time(0, 0), zone),
        local_moment(day + timedelta(days=1), time(0, 0), zone),
    )


def days_bounds(first: date, last: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """[start, end) from the start of first to the end of last (local)."""
    return day_bounds(first, zone)[0], day_bounds(last, zone)[1]


def night_window(now: datetime, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """The night the Morning check shows: 18:00 to 12:00 local. Before 18:00
    it is the night that ended (or ends) today at 12:00; from 18:00 on, the
    night that starts today."""
    today = local_date(now, zone)
    if now >= local_moment(today, NIGHT_START, zone):
        first = today
    else:
        first = today - timedelta(days=1)
    return (
        local_moment(first, NIGHT_START, zone),
        local_moment(first + timedelta(days=1), NIGHT_END, zone),
    )


def morning_line(
    start: datetime, end: datetime, zone: ZoneInfo, digest_time: time
) -> datetime | None:
    """The last digest time (the morning line of the ribbon) in [start, end),
    or None when the range holds none."""
    day = local_date(end, zone)
    while True:
        moment = local_moment(day, digest_time, zone)
        if moment < start:
            return None
        if moment < end:
            return moment
        day -= timedelta(days=1)


def digest_window(
    day: date, zone: ZoneInfo, digest_time: time
) -> tuple[datetime, datetime]:
    """The runs the digest of day reports: due in the 24 hours (local) up to
    the digest time of that day."""
    return (
        local_moment(day - timedelta(days=1), digest_time, zone),
        local_moment(day, digest_time, zone),
    )
