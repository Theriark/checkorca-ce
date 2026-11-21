"""Units of the schedule library: normal forms, bounds and the guard rails."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import reference
from app.schedule import (
    ScheduleError,
    ScheduleSpec,
    TooManyOccurrences,
    check_timezone,
    deadline,
    next_n,
    occurrences,
    parse_spec,
)
from app.schedule._cron import has_wildcard_hour
from app.schedule._wall import instants

MONDAY = datetime(2027, 1, 4, 9, 0, tzinfo=UTC)
LISBON = ZoneInfo("Europe/Lisbon")


@pytest.mark.parametrize(
    ("kind", "expr", "normal"),
    [
        ("cron", "  0   9 * *   1 ", "0 9 * * 1"),
        ("cron", "@HOURLY", "0 * * * *"),
        ("cron", "@weekly", "0 0 * * 0"),
        ("cron", "0 9 * JAN-MAR MON-FRI", "0 9 * JAN-MAR MON-FRI"),
        # croniter reads a range from a value to itself as a full cycle.
        ("cron", "0-0 5-5/2,7 * * MON-mon", "0 5,7 * * MON"),
        ("daily", "18:00, 6:00,06:00", "06:00,18:00"),
        ("daily", "23:00", "23:00"),
        ("interval", " 1H 30m ", "1h30m"),
        ("interval", "1d", "1d"),
    ],
)
def test_expressions_are_normalised(kind: str, expr: str, normal: str) -> None:
    spec = parse_spec(kind, expr, "Europe/Lisbon", MONDAY)
    assert spec.expr == normal
    assert spec.zone == LISBON


def test_only_an_interval_keeps_its_anchor() -> None:
    assert parse_spec("cron", "0 9 * * *", "UTC", MONDAY).anchor is None
    assert parse_spec("daily", "09:00", "UTC", MONDAY).anchor is None
    interval = parse_spec("interval", "1h30m", "UTC", MONDAY)
    assert interval.anchor == MONDAY
    assert interval.interval == timedelta(minutes=90)


def test_daily_times_are_hour_minute_pairs() -> None:
    spec = parse_spec("daily", "23:00, 06:30", "UTC")
    assert spec.daily_times == ((6, 30), (23, 0))


def test_check_timezone_trims_and_refuses() -> None:
    assert check_timezone(" Europe/Lisbon ") == "Europe/Lisbon"
    with pytest.raises(ScheduleError) as raised:
        check_timezone("x" * 65)
    assert raised.value.field == "timezone"


def test_the_wildcard_hour_rule() -> None:
    assert has_wildcard_hour("0 * * * *")
    assert has_wildcard_hour("0 */2 * * *")
    assert not has_wildcard_hour("0 1 * * *")
    assert not has_wildcard_hour("0 0-23 * * *")
    assert not has_wildcard_hour("0 1,13 * * *")


def test_wall_time_rules_in_lisbon() -> None:
    # Normal, gap (spring) and repeated (autumn) wall times.
    assert instants(datetime(2027, 1, 4, 23), LISBON, every_real_hour=False) == [
        datetime(2027, 1, 4, 23, tzinfo=UTC)
    ]
    gap = datetime(2027, 3, 28, 1, 30)
    assert instants(gap, LISBON, every_real_hour=False) == [
        datetime(2027, 3, 28, 1, tzinfo=UTC)
    ]
    # A * or */n hour follows cron: the skipped wall time does not fire (L1).
    assert instants(gap, LISBON, every_real_hour=True) == []
    repeated = datetime(2027, 10, 31, 1, 30)
    assert instants(repeated, LISBON, every_real_hour=False) == [
        datetime(2027, 10, 31, 0, 30, tzinfo=UTC)
    ]
    assert instants(repeated, LISBON, every_real_hour=True) == [
        datetime(2027, 10, 31, 0, 30, tzinfo=UTC),
        datetime(2027, 10, 31, 1, 30, tzinfo=UTC),
    ]


@pytest.mark.parametrize(
    ("expr", "zone", "start", "expected"),
    [
        # 01:30 Lisbon does not exist on 28 March 2027: no run for it.
        ("30 * * * *", "Europe/Lisbon", "2027-03-28T00:00", ["00:30", "01:30"]),
        ("*/20 * * * *", "Europe/Lisbon", "2027-03-28T00:00", ["00:00", "00:20"]),
        # 02:30 New York does not exist on 14 March 2027.
        ("30 * * * *", "America/New_York", "2027-03-14T05:00", ["05:30", "06:30"]),
        ("*/20 * * * *", "America/New_York", "2027-03-14T06:00", ["06:00", "06:20"]),
    ],
)
def test_an_every_hour_cron_follows_cron_in_the_spring_gap(
    expr: str, zone: str, start: str, expected: list[str]
) -> None:
    """L1 of the C3 review, decided in C7: a * or */n hour skips the wall
    times of the gap instead of firing at its end, as cron does, so the
    evaluator expects no extra run there. Compared with the reference too."""
    begin = datetime.fromisoformat(start).replace(tzinfo=UTC)
    end = begin + timedelta(hours=3)
    found = occurrences(parse_spec("cron", expr, zone), begin, end)
    assert found == reference.cron_occurrences(expr, zone, begin, end)
    times = [moment.strftime("%H:%M") for moment in found]
    assert times[: len(expected)] == expected
    gap_end = {"Europe/Lisbon": "01:00", "America/New_York": "07:00"}[zone]
    if not expr.startswith("*/"):
        assert gap_end not in times


def test_times_must_be_aware() -> None:
    spec = parse_spec("daily", "23:00", "UTC")
    with pytest.raises(ValueError, match="start"):
        occurrences(spec, datetime(2027, 1, 4), MONDAY)
    with pytest.raises(ValueError, match="after"):
        next_n(spec, datetime(2027, 1, 4), 1)
    with pytest.raises(ValueError, match="scheduled_for"):
        deadline(datetime(2027, 1, 4), 360, 120)


def test_an_empty_or_reversed_window_has_no_times() -> None:
    spec = parse_spec("cron", "* * * * *", "UTC")
    assert occurrences(spec, MONDAY, MONDAY) == []
    assert occurrences(spec, MONDAY, MONDAY - timedelta(hours=1)) == []
    assert next_n(spec, MONDAY, 0) == []


def test_offsets_other_than_utc_come_back_as_utc() -> None:
    spec = parse_spec("daily", "23:00", "Europe/Lisbon")
    start = datetime(2027, 7, 1, 12, tzinfo=LISBON)
    found = occurrences(spec, start, start + timedelta(days=1))
    assert found == [datetime(2027, 7, 1, 22, tzinfo=UTC)]
    assert found[0].tzinfo is UTC


def test_deadline_is_time_plus_runtime_plus_grace() -> None:
    scheduled = datetime(2027, 1, 4, 23, tzinfo=UTC)
    assert deadline(scheduled, 360, 120) == datetime(2027, 1, 5, 7, tzinfo=UTC)
    assert deadline(scheduled, 0, 0) == scheduled
    with pytest.raises(ValueError):
        deadline(scheduled, -1, 0)


def test_an_interval_spec_without_anchor_is_refused() -> None:
    spec = ScheduleSpec(kind="interval", expr="1h", timezone="UTC")
    with pytest.raises(ValueError, match="anchor"):
        occurrences(spec, MONDAY, MONDAY + timedelta(hours=3))
    with pytest.raises(ValueError, match="anchor"):
        next_n(spec, MONDAY, 1)


def test_a_huge_interval_window_is_refused_before_it_is_built() -> None:
    spec = parse_spec("interval", "1m", "UTC", MONDAY)
    with pytest.raises(TooManyOccurrences):
        occurrences(spec, MONDAY, MONDAY + timedelta(days=80))


def test_a_huge_cron_window_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.schedule.times.MAX_OCCURRENCES", 10)
    spec = parse_spec("cron", "* * * * *", "UTC")
    with pytest.raises(TooManyOccurrences):
        occurrences(spec, MONDAY, MONDAY + timedelta(hours=1))


@pytest.mark.parametrize(
    ("expr", "first"),
    [
        ("* * * 1-3 *", datetime(2027, 1, 1, tzinfo=UTC)),
        ("* * * 1,2 *", datetime(2027, 1, 1, tzinfo=UTC)),
        ("* * * * *", datetime(2026, 11, 19, 11, 55, tzinfo=UTC)),
    ],
)
def test_next_n_never_lists_the_whole_window(
    monkeypatch: pytest.MonkeyPatch, expr: str, first: datetime
) -> None:
    """Every minute of a few months, asked outside them (code review M1): next_n
    walks from `after` and stops at n, so the window cap is never reached."""
    monkeypatch.setattr("app.schedule.times.MAX_OCCURRENCES", 10)
    spec = parse_spec("cron", expr, "Europe/Lisbon")
    found = next_n(spec, datetime(2026, 11, 19, 11, 54, 30, tzinfo=UTC), 20)
    assert found == [first + timedelta(minutes=step) for step in range(20)]


def test_next_n_of_an_interval_is_arithmetic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.schedule.times.MAX_OCCURRENCES", 10)
    anchor = MONDAY + timedelta(days=30)
    spec = parse_spec("interval", "1m", "UTC", anchor)
    found = next_n(spec, MONDAY, 20)
    assert found == [anchor + timedelta(minutes=step) for step in range(1, 21)]
    rare = parse_spec("interval", "366d", "UTC", MONDAY)
    assert len(next_n(rare, MONDAY, 20)) == 9
