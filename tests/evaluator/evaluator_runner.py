"""Runs the golden scenarios of tests/evaluator/scenarios on the pure evaluator.

A scenario file holds a list of scenarios; each names a job and steps. A step
moves the injected FakeClock to its time, adds the results reported by then,
evaluates the job and writes the answer into an in-memory store (the stored
occurrences and the job_state record), as the worker does. Then it checks
what the step expects. Every step also checks, on its own:

- evaluating again at the same time changes nothing (idempotent);
- job state ok means the newest closed occurrence is verified.

Scenario format (times in UTC, ISO 8601):

  - name: nightly success is verified
    job:
      schedule: daily 23:00        # or "cron 0 * * * *", "interval 6h"
      timezone: Europe/Lisbon      # default Europe/Lisbon
      created: 2027-01-04T12:00:00Z
      max_runtime: 360             # minutes; grace, escalate, threshold,
      basis: finished              # warning_policy as in the job settings
      maintenance: [[start, end]]  # SuppressionProvider windows
    steps:
      - at: 2027-01-05T00:30:00Z
        suppressed: false          # paused or archived from this step on
        job: {grace: 60}           # job settings changed from this step on
        results:                   # reported by this step
          - {id: r1, status: success, finished: ..., received: ...}
        occurrences:               # by scheduled time: state, or
          2027-01-04T23:00:00Z: verified      # {state, note, result}
        absent: [2027-01-03T23:00:00Z]        # no occurrence at these times
        count: 1                   # stored occurrences in all
        state: ok                  # job state
        consecutive_failures: 0
        last_success_at: ...
        flips: [unknown>ok]        # flips made by this step, in order
        reason: Recovered          # text the step's last flip reason holds

All data is synthetic.
"""

import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.evaluator.machine import evaluate
from app.evaluator.model import (
    CLOSED_STATES,
    Evaluation,
    FlipDraft,
    JobRules,
    MaintenanceWindow,
    Occurrence,
    Result,
    StateRecord,
)
from app.schedule import parse_spec
from helpers import FakeClock

SCENARIOS = Path(__file__).parent / "scenarios"
NAMESPACE = uuid.UUID("6e55956e-0441-4c04-bd20-84bdaba1391c")
JOB_ID = uuid.uuid5(NAMESPACE, "job")
CLIENT_ID = uuid.uuid5(NAMESPACE, "client")
JOB_FIELDS = {
    "max_runtime": "max_runtime_minutes",
    "grace": "grace_minutes",
    "escalate": "escalate_minutes",
    "basis": "attribution_basis",
    "warning_policy": "warning_policy",
    "threshold": "consecutive_failures_to_alert",
}


def moment(value: Any) -> datetime:
    """A UTC time from YAML: a string, or the datetime YAML made of it."""
    if isinstance(value, datetime):
        found = value
    else:
        found = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if found.tzinfo is None:
        found = found.replace(tzinfo=UTC)
    return found.astimezone(UTC)


def result_id(label: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"result:{label}")


def load() -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for path in sorted(SCENARIOS.glob("*.yaml")):
        for scenario in yaml.safe_load(path.read_text(encoding="utf-8")):
            found.append({**scenario, "file": path.name})
    return found


def build_job(settings: dict[str, Any]) -> JobRules:
    kind, _, expr = str(settings["schedule"]).partition(" ")
    created = moment(settings["created"])
    zone = settings.get("timezone", "Europe/Lisbon")
    fields = {
        JOB_FIELDS[key]: value for key, value in settings.items() if key in JOB_FIELDS
    }
    return JobRules(
        id=JOB_ID,
        client_id=CLIENT_ID,
        spec=parse_spec(kind, expr, zone, created),
        created_at=created,
        **fields,
    )


def build_windows(settings: dict[str, Any]) -> list[MaintenanceWindow]:
    return [
        MaintenanceWindow(moment(start), moment(end))
        for start, end in settings.get("maintenance", [])
    ]


def build_result(item: dict[str, Any]) -> Result:
    return Result(
        id=result_id(str(item["id"])),
        status=item["status"],
        received_at=moment(item["received"]),
        started_at=moment(item["started"]) if "started" in item else None,
        finished_at=moment(item["finished"]) if "finished" in item else None,
    )


@dataclass
class Store:
    """The job's rows as the worker keeps them between ticks."""

    occurrences: dict[datetime, Occurrence] = field(default_factory=dict)
    record: StateRecord | None = None
    flips: list[FlipDraft] = field(default_factory=list)

    def apply(self, evaluation: Evaluation) -> None:
        for item in evaluation.deletes:
            del self.occurrences[item.scheduled_for]
        for item in evaluation.inserts:
            assert item.scheduled_for not in self.occurrences
            self.occurrences[item.scheduled_for] = item
        for old, new in evaluation.updates:
            assert self.occurrences[old.scheduled_for] == old
            self.occurrences[new.scheduled_for] = new
        self.record = evaluation.record
        if evaluation.flip is not None:
            self.flips.append(evaluation.flip)

    def stored(self) -> list[Occurrence]:
        return sorted(self.occurrences.values(), key=lambda item: item.scheduled_for)


@dataclass
class Run:
    """One scenario on the clock: the job, its results and the store."""

    job: JobRules
    windows: list[MaintenanceWindow]
    clock: FakeClock
    store: Store = field(default_factory=Store)
    results: list[Result] = field(default_factory=list)
    suppressed: bool = False

    def evaluate(self) -> Evaluation:
        return evaluate(
            self.job,
            self.store.record,
            self.store.stored(),
            self.results,
            self.clock.now(),
            suppressed=self.suppressed,
            windows=self.windows,
        )

    def step(self, step: dict[str, Any]) -> Evaluation:
        at = moment(step["at"])
        assert at >= self.clock.now(), "steps go forward in time"
        self.clock.advance(seconds=(at - self.clock.now()).total_seconds())
        if "suppressed" in step:
            self.suppressed = bool(step["suppressed"])
        if "job" in step:
            settings = dict(step["job"])
            schedule = settings.pop("schedule", None)
            changes = {JOB_FIELDS[key]: value for key, value in settings.items()}
            if schedule is not None:
                kind, _, expr = str(schedule).partition(" ")
                zone = self.job.spec.timezone
                changes["spec"] = parse_spec(kind, expr, zone, self.job.created_at)
            self.job = replace(self.job, **changes)
        self.results += [build_result(item) for item in step.get("results", [])]
        evaluation = self.evaluate()
        self.store.apply(evaluation)
        return evaluation


def start_run(scenario: dict[str, Any]) -> Run:
    settings = scenario["job"]
    first = moment(scenario["steps"][0]["at"])
    return Run(
        job=build_job(settings),
        windows=build_windows(settings),
        clock=FakeClock(first),
    )


def steps(scenario: dict[str, Any]) -> Iterator[tuple[dict[str, Any], Run, Evaluation]]:
    """Each step with the run after it and the step's evaluation."""
    run = start_run(scenario)
    for step in scenario["steps"]:
        evaluation = run.step(step)
        yield step, run, evaluation


def newest_closed(run: Run) -> Occurrence | None:
    now = run.clock.now()
    closed = [
        item
        for item in run.store.stored()
        if item.scheduled_for <= now and item.state in CLOSED_STATES
    ]
    return closed[-1] if closed else None


def check_invariants(run: Run) -> None:
    """Idempotent, and ok only with a verified newest closed occurrence."""
    again = run.evaluate()
    assert again.inserts == () and again.updates == () and again.deletes == ()
    assert again.flip is None
    assert again.record == run.store.record
    record = run.store.record
    assert record is not None
    if record.state == "ok":
        newest = newest_closed(run)
        assert newest is not None and newest.state == "verified"


def check_step(step: dict[str, Any], run: Run, evaluation: Evaluation) -> None:
    where = f"step at {step['at']}"
    stored = run.store.occurrences
    for at, expected in (step.get("occurrences") or {}).items():
        key = moment(at)
        assert key in stored, f"{where}: no occurrence at {at}"
        item = stored[key]
        wanted = expected if isinstance(expected, dict) else {"state": expected}
        assert item.state == wanted["state"], f"{where}: {at} is {item.state}"
        if "note" in wanted:
            assert item.note == wanted["note"], f"{where}: {at} note {item.note!r}"
        if "result" in wanted:
            label = wanted["result"]
            expected_id = None if label is None else result_id(str(label))
            assert item.result_id == expected_id, f"{where}: {at} result"
    for at in step.get("absent", []):
        assert moment(at) not in stored, f"{where}: occurrence at {at}"
    if "count" in step:
        assert len(stored) == step["count"], f"{where}: {len(stored)} occurrences"
    record = run.store.record
    assert record is not None
    if "state" in step:
        assert record.state == step["state"], f"{where}: state {record.state}"
    if "consecutive_failures" in step:
        assert record.consecutive_failures == step["consecutive_failures"]
    if "last_success_at" in step:
        wanted_time = step["last_success_at"]
        expected_time = None if wanted_time is None else moment(wanted_time)
        assert record.last_success_at == expected_time, f"{where}: last success"
    if "flips" in step:
        made = [] if evaluation.flip is None else [evaluation.flip]
        names = [f"{flip.from_state}>{flip.to_state}" for flip in made]
        assert names == step["flips"], f"{where}: flips {names}"
    if "reason" in step:
        assert evaluation.flip is not None, f"{where}: no flip"
        assert step["reason"] in evaluation.flip.reason, evaluation.flip.reason
    check_invariants(run)
