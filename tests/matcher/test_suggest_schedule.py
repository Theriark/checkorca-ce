"""suggest-schedule: the median local time of a job's runs as a daily schedule.

Golden cases: plain nights, both DST changes in Lisbon and New York, runs
around midnight, rounding, the basis, and too few runs.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.matcher import RunTimes, TooFewResults, circular_median, suggest_daily


def at(text: str) -> datetime:
    return datetime.fromisoformat(text)


def run(received: str, *, finished: str = "", started: str = "") -> RunTimes:
    return RunTimes(
        received_at=at(received),
        started_at=at(started) if started else None,
        finished_at=at(finished) if finished else None,
    )


def finished(*times: str) -> list[RunTimes]:
    return [run(time, finished=time) for time in times]


GOLDEN = [
    (
        "three winter nights in Lisbon",
        finished(
            "2027-01-04T23:12:00Z", "2027-01-05T23:08:00Z", "2027-01-06T23:10:00Z"
        ),
        "Europe/Lisbon",
        "23:10",
    ),
    (
        # Lisbon moves to summer time on 28 March 2027: 23:00 local is 23:00Z,
        # then 22:00Z.
        "23:00 in Lisbon across the spring change",
        finished(
            "2027-03-26T23:00:00Z",
            "2027-03-27T23:01:00Z",
            "2027-03-28T22:02:00Z",
            "2027-03-29T22:00:00Z",
        ),
        "Europe/Lisbon",
        "23:00",
    ),
    (
        # Back to winter time on 31 October 2027; 01:30 local happens twice
        # that night, the first run is the summer one.
        "01:30 in Lisbon across the autumn change",
        finished(
            "2027-10-30T00:30:00Z", "2027-10-31T00:31:00Z", "2027-11-01T01:32:00Z"
        ),
        "Europe/Lisbon",
        "01:30",
    ),
    (
        "06:00 in New York across the spring change",
        finished(
            "2027-03-13T11:00:00Z", "2027-03-14T10:03:00Z", "2027-03-15T10:01:00Z"
        ),
        "America/New_York",
        "06:00",
    ),
    (
        "runs around midnight",
        finished(
            "2027-01-04T23:50:00Z", "2027-01-06T00:10:00Z", "2027-01-06T23:55:00Z"
        ),
        "UTC",
        "23:55",
    ),
    (
        "the lower median of an even count",
        finished(
            "2027-01-04T02:00:00Z",
            "2027-01-05T02:10:00Z",
            "2027-01-06T02:20:00Z",
            "2027-01-07T02:30:00Z",
        ),
        "UTC",
        "02:10",
    ),
    (
        "rounded down to five minutes",
        finished(
            "2027-01-04T04:47:00Z", "2027-01-05T04:48:00Z", "2027-01-06T04:49:00Z"
        ),
        "UTC",
        "04:45",
    ),
]


@pytest.mark.parametrize(
    ("runs", "zone", "expr"),
    [case[1:] for case in GOLDEN],
    ids=[case[0] for case in GOLDEN],
)
def test_golden_suggestions(runs: list[RunTimes], zone: str, expr: str) -> None:
    suggestion = suggest_daily(runs, ZoneInfo(zone))
    assert (suggestion.kind, suggestion.expr) == ("daily", expr)
    assert suggestion.timezone == zone
    assert suggestion.basis == "finished"
    assert suggestion.results == len(runs)


def test_the_basis_falls_back_to_started_then_received() -> None:
    days = (4, 5, 6)
    started = [
        run(f"2027-01-0{day}T07:00:00Z", started=f"2027-01-0{day}T05:00:00Z")
        for day in days
    ]
    suggestion = suggest_daily(started, ZoneInfo("UTC"))
    assert (suggestion.basis, suggestion.expr) == ("started", "05:00")
    received = [run(f"2027-01-0{day}T07:20:00Z") for day in days]
    suggestion = suggest_daily(received, ZoneInfo("UTC"))
    assert (suggestion.basis, suggestion.expr) == ("received", "07:20")


def test_half_of_the_runs_with_a_finish_time_is_enough() -> None:
    runs = [
        run("2027-01-04T07:00:00Z", finished="2027-01-04T03:00:00Z"),
        run("2027-01-05T07:00:00Z", finished="2027-01-05T03:05:00Z"),
        run("2027-01-06T07:00:00Z", finished="2027-01-06T03:10:00Z"),
        run("2027-01-07T07:00:00Z"),
        run("2027-01-08T07:00:00Z"),
        run("2027-01-09T07:00:00Z"),
    ]
    suggestion = suggest_daily(runs, ZoneInfo("UTC"))
    assert (suggestion.basis, suggestion.expr, suggestion.results) == (
        "finished",
        "03:05",
        3,
    )
    # Fewer than half: the receive times, which every run has.
    suggestion = suggest_daily([*runs, runs[-1]], ZoneInfo("UTC"))
    assert (suggestion.basis, suggestion.expr, suggestion.results) == (
        "received",
        "07:00",
        7,
    )


def test_too_few_runs_give_no_suggestion() -> None:
    two = finished("2027-01-04T23:00:00Z", "2027-01-05T23:00:00Z")
    with pytest.raises(TooFewResults, match="at least 3"):
        suggest_daily(two, ZoneInfo("UTC"))
    with pytest.raises(TooFewResults):
        suggest_daily([], ZoneInfo("UTC"), minimum=0)
    # create-job takes what there is.
    one = suggest_daily(two[:1], ZoneInfo("Europe/Lisbon"), minimum=1)
    assert (one.expr, one.results) == ("23:00", 1)


def test_circular_median() -> None:
    assert circular_median([600]) == 600
    assert circular_median([1430, 10, 1435]) == 1435
    assert circular_median([0, 0, 0]) == 0
    assert circular_median([1439, 1, 1441]) == 1
    with pytest.raises(TooFewResults):
        circular_median([])
