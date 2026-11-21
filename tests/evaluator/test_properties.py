"""Property tests of the pure evaluator on random histories (synthetic).

A history is a job, then evaluations at increasing times, each after some
results arrived and with the job paused or not. After every evaluation:

- evaluating again at the same time changes nothing (idempotent);
- job state ok means the newest closed occurrence is verified;
- no occurrence is verified without a success (or a warning under
  warning_counts_ok), and an unknown result never verifies one.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import evaluator_runner as runner
from app.evaluator.machine import window_start
from app.evaluator.model import JobRules, Occurrence, Result
from app.ingest.results import RESULT_STATUSES
from app.schedule import parse_spec
from helpers import FakeClock

# Around the 2027 DST changes of Lisbon and New York, and a quiet day.
DAYS = (
    datetime(2027, 3, 13, 12, tzinfo=UTC),
    datetime(2027, 3, 27, 12, tzinfo=UTC),
    datetime(2027, 10, 30, 12, tzinfo=UTC),
    datetime(2027, 11, 6, 12, tzinfo=UTC),
    datetime(2027, 6, 15, 12, tzinfo=UTC),
)
ZONES = ("Europe/Lisbon", "America/New_York", "UTC")
PROFILE = settings(
    max_examples=150,
    deadline=None,
    derandomize=True,
    suppress_health_check=[HealthCheck.too_slow],
)


@st.composite
def jobs(draw: st.DrawFn) -> JobRules:
    created = draw(st.sampled_from(DAYS)) - timedelta(
        minutes=draw(st.integers(0, 3 * 24 * 60))
    )
    zone = draw(st.sampled_from(ZONES))
    if draw(st.booleans()):
        hour = draw(st.integers(0, 23))
        minute = draw(st.sampled_from([0, 30]))
        spec = parse_spec("daily", f"{hour:02d}:{minute:02d}", zone)
    else:
        spec = parse_spec("interval", f"{draw(st.integers(2, 30))}h", zone, created)
    return JobRules(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        spec=spec,
        created_at=created,
        max_runtime_minutes=draw(st.integers(1, 600)),
        grace_minutes=draw(st.integers(0, 240)),
        escalate_minutes=draw(st.integers(0, 120)),
        attribution_basis=draw(st.sampled_from(["started", "finished", "received"])),
        warning_policy=draw(
            st.sampled_from(["warning_is_attention", "warning_counts_ok"])
        ),
        consecutive_failures_to_alert=draw(st.integers(1, 3)),
    )


@st.composite
def results(draw: st.DrawFn, at: datetime) -> Result:
    """A result received before at, possibly with start and finish times."""
    received = at - timedelta(minutes=draw(st.integers(0, 36 * 60)))
    finished = received - timedelta(minutes=draw(st.integers(0, 90)))
    started = finished - timedelta(minutes=draw(st.integers(0, 600)))
    return Result(
        id=uuid.uuid4(),
        status=draw(st.sampled_from(RESULT_STATUSES)),
        received_at=received,
        started_at=started if draw(st.booleans()) else None,
        finished_at=finished if draw(st.booleans()) else None,
    )


@st.composite
def histories(draw: st.DrawFn) -> dict[str, Any]:
    job = draw(jobs())
    at = job.created_at + timedelta(minutes=draw(st.integers(0, 24 * 60)))
    steps = []
    for _ in range(draw(st.integers(1, 8))):
        at += timedelta(minutes=draw(st.integers(1, 20 * 60)))
        found = draw(st.lists(results(at), max_size=3))
        steps.append({"at": at, "results": found, "paused": draw(st.booleans())})
    return {"job": job, "steps": steps}


def replay(history: dict[str, Any]) -> runner.Run:
    steps = history["steps"]
    run = runner.Run(job=history["job"], windows=[], clock=FakeClock(steps[0]["at"]))
    for step in steps:
        run.clock.advance(seconds=(step["at"] - run.clock.now()).total_seconds())
        # Paused in a fifth of the steps: drawn often, applied rarely.
        run.suppressed = step["paused"] and step["at"].minute % 5 == 0
        run.results += step["results"]
        run.store.apply(run.evaluate())
        runner.check_invariants(run)
        check_verified(run)
    return run


def in_window(run: runner.Run, start: datetime) -> list[Occurrence]:
    return [item for item in run.store.stored() if item.scheduled_for >= start]


def check_verified(run: runner.Run) -> None:
    by_id = {result.id: result for result in run.results}
    for item in run.store.stored():
        if item.state != "verified":
            continue
        assert item.result_id is not None
        status = by_id[item.result_id].status
        if status == "warning":
            assert run.job.warning_policy == "warning_counts_ok"
        else:
            assert status == "success"


@PROFILE
@given(history=histories())
def test_ok_means_the_newest_closed_occurrence_is_verified(
    history: dict[str, Any],
) -> None:
    replay(history)


@PROFILE
@given(history=histories())
def test_one_evaluation_after_all_the_steps_gives_the_same_state(
    history: dict[str, Any],
) -> None:
    """Evaluating once at the end, from nothing, gives the same occurrences as
    evaluating at every step (no pause involved): the state depends on the
    results and the time, not on when the worker looked."""
    for step in history["steps"]:
        step["paused"] = False
    stepped = replay(history)
    last = history["steps"][-1]["at"]
    once = runner.Run(job=history["job"], windows=[], clock=FakeClock(last))
    once.results = list(stepped.results)
    once.store.apply(once.evaluate())
    start = window_start(history["job"], last)
    assert in_window(once, start) == in_window(stepped, start)
    record, expected = once.store.record, stepped.store.record
    assert record is not None and expected is not None
    assert (record.state, record.consecutive_failures) == (
        expected.state,
        expected.consecutive_failures,
    )
