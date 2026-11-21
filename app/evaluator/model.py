"""The evaluator's values: what it reads about a job and what it decides.

Plain frozen dataclasses without database types, so the state machine
(app/evaluator/machine.py) is pure and the golden scenarios run on them. The
fields of Occurrence and of a flip follow the Interfaces chapter (Evaluation);
phases C8-B (dashboard, ribbon, digest) and C9-B (notifications) build on them.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal, cast

from app.ingest.results import ResultStatus
from app.schedule import ScheduleSpec

OccurrenceState = Literal[
    "pending",
    "running",
    "verified",
    "warning",
    "failed",
    "overdue",
    "missed",
    "maintenance",
]
OCCURRENCE_STATES: Final[tuple[OccurrenceState, ...]] = (
    "pending",
    "running",
    "verified",
    "warning",
    "failed",
    "overdue",
    "missed",
    "maintenance",
)
# Still waiting for a final result: time alone can change them.
OPEN_STATES: Final[frozenset[OccurrenceState]] = frozenset(
    {"pending", "running", "overdue"}
)
# Have an outcome; the job state derives from the newest of them.
CLOSED_STATES: Final[frozenset[OccurrenceState]] = frozenset(
    {"verified", "warning", "failed", "missed", "maintenance"}
)
# Silent means overdue or missed (Interfaces chapter).
SILENT_STATES: Final[frozenset[OccurrenceState]] = frozenset({"overdue", "missed"})

JobState = Literal[
    "ok", "warning", "failing", "missed", "unknown", "paused", "maintenance"
]
JOB_STATES: Final[tuple[JobState, ...]] = (
    "ok",
    "warning",
    "failing",
    "missed",
    "unknown",
    "paused",
    "maintenance",
)

AttributionBasis = Literal["started", "finished", "received"]
WarningPolicy = Literal["warning_is_attention", "warning_counts_ok"]
_BASES: Final[tuple[AttributionBasis, ...]] = ("started", "finished", "received")
_POLICIES: Final[tuple[WarningPolicy, ...]] = (
    "warning_is_attention",
    "warning_counts_ok",
)


def as_basis(value: str) -> AttributionBasis:
    """A stored attribution basis, checked (the table allows only these)."""
    if value not in _BASES:
        raise ValueError(f"unknown attribution basis {value!r}")
    return cast(AttributionBasis, value)


def as_policy(value: str) -> WarningPolicy:
    """A stored warning policy, checked."""
    if value not in _POLICIES:
        raise ValueError(f"unknown warning policy {value!r}")
    return cast(WarningPolicy, value)


def as_job_state(value: str) -> JobState:
    """A stored job state, checked."""
    if value not in JOB_STATES:
        raise ValueError(f"unknown job state {value!r}")
    return cast(JobState, value)


def as_occurrence_state(value: str) -> OccurrenceState:
    """A stored occurrence state, checked."""
    if value not in OCCURRENCE_STATES:
        raise ValueError(f"unknown occurrence state {value!r}")
    return cast(OccurrenceState, value)


@dataclass(frozen=True, slots=True)
class JobRules:
    """A job as the evaluator sees it: its schedule and its time rules.

    spec is the job's schedule; an interval schedule is anchored on created_at.
    """

    id: uuid.UUID
    client_id: uuid.UUID
    spec: ScheduleSpec
    created_at: datetime
    max_runtime_minutes: int = 360
    grace_minutes: int = 120
    escalate_minutes: int = 30
    attribution_basis: AttributionBasis = "finished"
    warning_policy: WarningPolicy = "warning_is_attention"
    consecutive_failures_to_alert: int = 1

    @property
    def escalation(self) -> timedelta:
        return timedelta(minutes=self.escalate_minutes)


@dataclass(frozen=True, slots=True)
class Result:
    """One reported run of the job (a row of job_result bound to it)."""

    id: uuid.UUID
    status: ResultStatus
    received_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def basis(self, basis: AttributionBasis) -> datetime:
        """The time the result is attributed by; received when the one the
        job asks for is missing."""
        if basis == "started" and self.started_at is not None:
            return self.started_at
        if basis == "finished" and self.finished_at is not None:
            return self.finished_at
        return self.received_at

    @property
    def ended_at(self) -> datetime:
        """When the run ended, as far as the result says (last_success_at)."""
        return self.finished_at or self.received_at


@dataclass(frozen=True, slots=True)
class Occurrence:
    """One expected run: when it was due, its deadline and what happened.

    result_id is the result that decided the state (the latest final result,
    or the start of a run without a final result yet). note explains a state
    in a few words (recovered after retry, late result, started, never
    finished).
    """

    scheduled_for: datetime
    deadline: datetime
    state: OccurrenceState
    result_id: uuid.UUID | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class MaintenanceWindow:
    """A time range [start, end) in which a job's runs are not expected
    (SuppressionProvider). An occurrence due inside it is maintenance."""

    start: datetime
    end: datetime

    def covers(self, moment: datetime) -> bool:
        return self.start <= moment < self.end


@dataclass(frozen=True, slots=True)
class StateRecord:
    """What the evaluator keeps about a job between ticks (table job_state).

    eval_from: occurrences start here, the end of the last pause or archive
    (None: at the job's creation). suppressed: the job was paused or archived,
    or its client archived, when it was last evaluated.
    """

    state: JobState = "unknown"
    since: datetime | None = None
    consecutive_failures: int = 0
    last_success_at: datetime | None = None
    eval_from: datetime | None = None
    suppressed: bool = False


@dataclass(frozen=True, slots=True)
class FlipDraft:
    """A change of the job state; the store gives it an id, a time and the
    client. scheduled_for is the occurrence that caused it, if any."""

    from_state: JobState
    to_state: JobState
    reason: str
    scheduled_for: datetime | None = None


@dataclass(frozen=True, slots=True)
class Evaluation:
    """What one evaluation of one job decided.

    updates pairs each stored occurrence with its new value. due_at is the
    next moment time alone changes something (a deadline, an escalation, the
    next occurrence to write); None while the job is suppressed.
    """

    inserts: tuple[Occurrence, ...]
    updates: tuple[tuple[Occurrence, Occurrence], ...]
    deletes: tuple[Occurrence, ...]
    record: StateRecord
    flip: FlipDraft | None
    due_at: datetime | None

    @property
    def occurrence_rows(self) -> int:
        """Occurrence rows this evaluation writes or deletes."""
        return len(self.inserts) + len(self.updates) + len(self.deletes)
