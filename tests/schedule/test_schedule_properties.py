"""Property tests: scheduled times are monotonic and unique, independent of
the query window, and equal to the minute-by-minute reference (reference.py).
"""

from datetime import UTC, datetime, timedelta
from itertools import pairwise

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import reference
from app.schedule import ScheduleSpec, next_n, occurrences, parse_spec

ZONES = (
    "Europe/Lisbon",
    "Europe/London",
    "America/New_York",
    "UTC",
    "Australia/Lord_Howe",  # 30-minute DST change
    "Antarctica/Troll",  # 2-hour DST change: next_n's one-hour probes (L4)
    "Asia/Kolkata",
)
# Around the 2027 changes of the zones above, and a quiet day.
DAYS = (
    datetime(2027, 3, 14, tzinfo=UTC),
    datetime(2027, 3, 28, tzinfo=UTC),
    datetime(2027, 4, 4, tzinfo=UTC),
    datetime(2027, 10, 3, tzinfo=UTC),
    datetime(2027, 10, 31, tzinfo=UTC),
    datetime(2027, 11, 7, tzinfo=UTC),
    datetime(2027, 6, 15, tzinfo=UTC),
)
# Derandomized: the merge gate sees the same examples on every run.
PROFILE = settings(
    max_examples=60,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)


def field(low: int, high: int) -> st.SearchStrategy[str]:
    value = st.integers(low, high)
    return st.one_of(
        st.just("*"),
        st.integers(1, max(1, (high - low) // 2)).map(lambda step: f"*/{step}"),
        value.map(str),
        st.tuples(value, value).map(lambda pair: f"{min(pair)}-{max(pair)}"),
        st.lists(value, min_size=2, max_size=3, unique=True).map(
            lambda items: ",".join(map(str, sorted(items)))
        ),
    )


# Day of month and month stay wide, so most expressions fire inside a few days.
cron_expressions = st.tuples(
    field(0, 59),
    field(0, 23),
    st.sampled_from(["*", "*", "1-28", "*/2"]),
    st.just("*"),
    st.sampled_from(["*", "*", "1-5", "0,6"]),
).map(" ".join)

daily_lists = st.lists(
    st.tuples(st.integers(0, 23), st.integers(0, 59)), min_size=1, max_size=4
).map(lambda items: ", ".join(f"{hour:02d}:{minute:02d}" for hour, minute in items))

windows = st.tuples(
    st.sampled_from(DAYS),
    st.integers(-36 * 60, 36 * 60),
    st.integers(1, 3 * 24 * 60),
).map(
    lambda parts: (
        parts[0] + timedelta(minutes=parts[1]),
        parts[0] + timedelta(minutes=parts[1] + parts[2]),
    )
)


@st.composite
def specs(draw: st.DrawFn) -> ScheduleSpec:
    kind = draw(st.sampled_from(["cron", "daily", "interval"]))
    zone = draw(st.sampled_from(ZONES))
    if kind == "cron":
        return parse_spec("cron", draw(cron_expressions), zone)
    if kind == "daily":
        return parse_spec("daily", draw(daily_lists), zone)
    minutes = draw(st.integers(1, 3 * 24 * 60))
    anchor = draw(st.sampled_from(DAYS)) - timedelta(
        minutes=draw(st.integers(0, 10 * 24 * 60)), seconds=draw(st.integers(0, 59))
    )
    return parse_spec("interval", f"{minutes}m", zone, anchor)


@PROFILE
@given(spec=specs(), window=windows)
def test_occurrences_are_monotonic_unique_and_inside_the_window(
    spec: ScheduleSpec, window: tuple[datetime, datetime]
) -> None:
    start, end = window
    found = occurrences(spec, start, end)
    assert all(earlier < later for earlier, later in pairwise(found))
    assert all(start <= value < end for value in found)
    assert all(value.utcoffset() == timedelta(0) for value in found)


@PROFILE
@given(spec=specs(), window=windows, cut=st.floats(0, 1))
def test_a_split_window_gives_the_same_times(
    spec: ScheduleSpec, window: tuple[datetime, datetime], cut: float
) -> None:
    """The DST rules depend on the wall time only, never on where a query
    starts: the evaluator can compute occurrences lazily in any windows."""
    start, end = window
    middle = start + (end - start) * cut
    whole = occurrences(spec, start, end)
    assert occurrences(spec, start, middle) + occurrences(spec, middle, end) == whole


@PROFILE
@given(spec=specs(), window=windows, count=st.integers(1, 8))
def test_next_n_continues_the_occurrences(
    spec: ScheduleSpec, window: tuple[datetime, datetime], count: int
) -> None:
    after, _ = window
    found = next_n(spec, after, count)
    assert len(found) == count
    assert all(value > after for value in found)
    listed = occurrences(spec, after, found[-1] + timedelta(seconds=1))
    assert found == listed[-count:]
    assert occurrences(spec, after + timedelta(microseconds=1), found[0]) == []


@PROFILE
@given(
    expression=cron_expressions,
    zone=st.sampled_from(ZONES),
    window=windows,
)
def test_cron_equals_the_minute_by_minute_reference(
    expression: str, zone: str, window: tuple[datetime, datetime]
) -> None:
    start, end = window
    spec = parse_spec("cron", expression, zone)
    assert occurrences(spec, start, end) == reference.cron_occurrences(
        expression, zone, start, end
    )


@PROFILE
@given(times=daily_lists, zone=st.sampled_from(ZONES), window=windows)
def test_daily_equals_the_minute_by_minute_reference(
    times: str, zone: str, window: tuple[datetime, datetime]
) -> None:
    start, end = window
    spec = parse_spec("daily", times, zone)
    assert occurrences(spec, start, end) == reference.daily_occurrences(
        times, zone, start, end
    )
