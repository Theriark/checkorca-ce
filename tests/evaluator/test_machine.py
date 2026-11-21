"""Units of the pure evaluator (app/evaluator/machine.py and model.py) that the
golden scenarios do not reach directly. Synthetic data."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from app.evaluator import machine
from app.evaluator.machine import (
    ATTRIBUTION_SLACK,
    LOOKAHEAD,
    REASON_LENGTH,
    WINDOW,
    Derived,
    attribute,
    derive_state,
    evaluate,
    flip_reason,
    next_due,
    window_start,
)
from app.evaluator.model import (
    Evaluation,
    JobRules,
    MaintenanceWindow,
    Occurrence,
    Result,
    StateRecord,
    as_basis,
    as_job_state,
    as_occurrence_state,
    as_policy,
)
from app.schedule import parse_spec

CREATED = datetime(2027, 1, 4, 12, tzinfo=UTC)
NIGHT = datetime(2027, 1, 4, 23, tzinfo=UTC)
DEADLINE = NIGHT + timedelta(hours=8)


def nightly(**settings: Any) -> JobRules:
    spec = parse_spec("daily", "23:00", "Europe/Lisbon")
    return JobRules(
        id=uuid.uuid4(),
        client_id=uuid.uuid4(),
        spec=spec,
        created_at=CREATED,
        **settings,
    )


def success(at: datetime) -> Result:
    return Result(id=uuid.uuid4(), status="success", received_at=at, finished_at=at)


def test_stored_values_are_checked() -> None:
    assert as_basis("started") == "started"
    assert as_policy("warning_counts_ok") == "warning_counts_ok"
    assert as_job_state("failing") == "failing"
    assert as_occurrence_state("overdue") == "overdue"
    for check in (as_basis, as_policy, as_job_state, as_occurrence_state):
        with pytest.raises(ValueError, match="unknown"):
            check("sometimes")


def test_the_window_is_14_days_unless_a_run_can_take_longer() -> None:
    now = datetime(2027, 2, 1, tzinfo=UTC)
    assert window_start(nightly(), now) == now - WINDOW
    long = nightly(max_runtime_minutes=10080, grace_minutes=10080, escalate_minutes=60)
    assert window_start(long, now) == now - timedelta(days=15, hours=1)


def test_attribution_boundaries() -> None:
    times = [NIGHT - timedelta(days=1), NIGHT]
    exact = success(NIGHT - ATTRIBUTION_SLACK)
    early = success(NIGHT - ATTRIBUTION_SLACK - timedelta(seconds=1))
    before = success(times[0] - ATTRIBUTION_SLACK - timedelta(seconds=1))
    found = attribute(times, [exact, early, before], "finished")
    assert found == {NIGHT: [exact], times[0]: [early]}
    assert attribute([], [exact], "finished") == {}


def test_a_maintenance_window_is_half_open() -> None:
    window = MaintenanceWindow(NIGHT, NIGHT + timedelta(hours=1))
    assert window.covers(NIGHT)
    assert not window.covers(NIGHT + timedelta(hours=1))
    assert not window.covers(NIGHT - timedelta(microseconds=1))


def test_derive_state_without_closed_runs_is_unknown() -> None:
    pending = Occurrence(NIGHT, DEADLINE, "pending")
    assert derive_state([pending], DEADLINE, 1) == Derived("unknown", 0, None)
    # A closed run due in the future does not count yet.
    early = Occurrence(NIGHT, DEADLINE, "verified")
    assert derive_state([early], NIGHT - timedelta(minutes=1), 1).state == "unknown"


def test_flip_reasons() -> None:
    assert flip_reason("ok", Derived("unknown", 0, None), 1) == (
        "No run has an outcome in the evaluated window"
    )
    long = Occurrence(NIGHT, DEADLINE, "failed", note="x" * 400)
    text = flip_reason("ok", Derived("failing", 1, long), 1)
    assert len(text) == REASON_LENGTH
    assert text.endswith("…")
    assert text.startswith("The run due 2027-01-04T23:00:00Z failed")


def test_next_due_is_the_nearest_deadline_escalation_or_new_run() -> None:
    job = nightly()
    now = NIGHT + timedelta(hours=1)
    pending = Occurrence(NIGHT, DEADLINE, "pending")
    assert next_due(job, [pending], now) == DEADLINE
    overdue = Occurrence(NIGHT, DEADLINE, "overdue")
    escalation = DEADLINE + timedelta(minutes=30)
    assert next_due(job, [overdue], DEADLINE) == escalation
    # Nothing open: the next night is written LOOKAHEAD before it is due.
    verified = Occurrence(NIGHT, DEADLINE, "verified")
    assert next_due(job, [verified], now) == NIGHT + timedelta(days=1) - LOOKAHEAD


def test_due_at_comes_after_now() -> None:
    job = nightly()
    for minutes in range(0, 24 * 60, 7):
        now = NIGHT + timedelta(minutes=minutes)
        evaluation = evaluate(job, None, [], [], now)
        assert evaluation.due_at is not None and evaluation.due_at > now


def test_stored_runs_older_than_the_window_are_left_alone() -> None:
    job = nightly()
    now = NIGHT + timedelta(days=30)
    old = Occurrence(NIGHT, DEADLINE, "pending")
    evaluation = evaluate(job, StateRecord(), [old], [], now)
    assert old not in evaluation.deletes
    assert all(item.scheduled_for != NIGHT for item in evaluation.inserts)


def test_a_suppressed_job_only_drops_open_runs() -> None:
    job = nightly()
    closed = Occurrence(NIGHT - timedelta(days=1), DEADLINE, "verified")
    open_run = Occurrence(NIGHT, DEADLINE, "overdue")
    record = StateRecord(state="ok", since=NIGHT)
    evaluation = evaluate(
        job, record, [closed, open_run], [], DEADLINE, suppressed=True
    )
    assert evaluation == Evaluation(
        inserts=(),
        updates=(),
        deletes=(open_run,),
        record=StateRecord(state="ok", since=NIGHT, suppressed=True),
        flip=None,
        due_at=None,
    )
    assert evaluation.occurrence_rows == 1


def test_the_first_evaluation_starts_the_state_now() -> None:
    now = NIGHT - timedelta(hours=1)
    evaluation = evaluate(nightly(), None, [], [], now)
    assert evaluation.record == StateRecord(state="unknown", since=now)
    assert evaluation.flip is None


def test_resuming_sets_where_runs_start_again() -> None:
    now = DEADLINE + timedelta(hours=3)
    record = StateRecord(state="ok", since=CREATED, suppressed=True)
    evaluation = evaluate(nightly(), record, [], [], now)
    assert evaluation.record.eval_from == now
    assert evaluation.record.suppressed is False
    assert evaluation.inserts == ()


def test_notes_are_clipped() -> None:
    assert machine._clip(None, 5) is None
    assert machine._clip("abc", 5) == "abc"
    assert machine._clip("abcdef", 5) == "abcd…"
