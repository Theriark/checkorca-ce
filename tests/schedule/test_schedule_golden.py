"""Golden tables: scheduled times across both DST changes, leap days, interval
anchors and invalid input (tests/schedule/golden).

Each window case lists the expected instants in UTC and, for the reader, the
same instants in local time with their offset. The tables were produced by the
minute-by-minute walk of reference.py, then checked by hand against the DST
policy (rnd-report-2 5.5) and the croniter findings of docs/spikes.md.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from app.schedule import ScheduleError, next_n, occurrences, parse_spec

GOLDEN = Path(__file__).parent / "golden"
WINDOW_FILES = (
    "europe_lisbon",
    "europe_london",
    "america_new_york",
    "utc",
    "interval",
)


def load(name: str) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(
        (GOLDEN / f"{name}.json").read_text(encoding="utf-8")
    )["cases"]
    return cases


def moment(text: str | None) -> datetime | None:
    return None if text is None else datetime.fromisoformat(text)


def utc_text(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


WINDOW_CASES = [(name, case) for name in WINDOW_FILES for case in load(name)]


@pytest.mark.parametrize(
    ("file", "case"),
    WINDOW_CASES,
    ids=[f"{name}: {case['name']}" for name, case in WINDOW_CASES],
)
def test_occurrences_in_a_window(file: str, case: dict[str, Any]) -> None:
    spec = parse_spec(
        case["kind"], case["expr"], case["timezone"], moment(case.get("anchor"))
    )
    start, end = moment(case["start"]), moment(case["end"])
    assert start is not None and end is not None
    found = occurrences(spec, start, end)
    assert [utc_text(value) for value in found] == case["expected"]
    zone = ZoneInfo(case["timezone"])
    assert [value.astimezone(zone).isoformat() for value in found] == case["local"]


@pytest.mark.parametrize("case", load("next_n"), ids=lambda case: case["name"])
def test_next_n(case: dict[str, Any]) -> None:
    spec = parse_spec(
        case["kind"], case["expr"], case["timezone"], moment(case.get("anchor"))
    )
    after = moment(case["after"])
    assert after is not None
    found = next_n(spec, after, case["count"])
    assert [utc_text(value) for value in found] == case["expected"]


@pytest.mark.parametrize("case", load("invalid"), ids=lambda case: case["name"])
def test_invalid_input_names_the_field(case: dict[str, Any]) -> None:
    with pytest.raises(ScheduleError) as raised:
        parse_spec(
            case["kind"], case["expr"], case["timezone"], moment(case.get("anchor"))
        )
    assert raised.value.field == case["field"]
    # A sentence for the user, never a stack trace or library internals.
    assert raised.value.message.endswith(".")
    assert "croniter" not in raised.value.message.lower()


def test_the_zone_tables_cover_both_changes() -> None:
    for name in ("europe_lisbon", "europe_london", "america_new_york"):
        offsets = {
            datetime.fromisoformat(local).utcoffset()
            for case in load(name)
            for local in case["local"]
        }
        assert len(offsets) == 2, name
    names = [case["name"] for case in load("utc")]
    assert any("leap day" in name for name in names)
