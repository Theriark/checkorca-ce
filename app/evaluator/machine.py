"""The expected-run algorithm of rnd-report-2 5.5, as pure functions.

evaluate() takes one job, what is stored about it, its results and the time,
and returns what must change. It reads no clock and no database: the same
input gives the same answer, and evaluating again after the answer was
written changes nothing (idempotent).

1. Occurrences are the job's scheduled times (app/schedule, with its DST
   policy) from the latest of: 14 days ago, the job's creation and the end of
   its last pause or archive; up to LOOKAHEAD ahead, so a run that reports a
   little early finds its occurrence. A job whose runtime, grace and
   escalation add up to more than 13 days looks back further, until its
   occurrences can no longer change.
2. Deadline d = scheduled time + max runtime + grace (app/schedule.deadline).
3. Attribution: a result belongs to the latest occurrence t with t <= x + 10
   minutes, x its basis time (started, finished or received as the job says;
   received when that time is missing). A result before the first occurrence
   stays in history only.
4. An occurrence is maintenance when the SuppressionProvider puts it in a
   window; otherwise the latest final result (success, warning, failed)
   decides: verified, warning (verified under warning_counts_ok) or failed;
   failed then success is verified, "recovered after retry". Without a final
   result it is pending (or running after a start) before d, overdue from d
   and missed from d + escalation. Unknown results never verify anything.
5. The job state derives from the newest closed occurrence (verified,
   warning, failed, missed, maintenance) and the count of consecutive failed
   or missed ones: ok, warning, maintenance, unknown (none closed yet), and
   failing or missed once the count reaches consecutive_failures_to_alert;
   below the threshold a failure shows as warning. Every change of the job
   state is one flip; a late success turns missed into verified and the job
   state back to ok, which is the recovery flip. The state looks past the
   window: the newest closed occurrence before it, and the newest
   consecutive_failures_to_alert closed ones that are not maintenance, so a
   weekly or monthly job keeps its state and its count of failures when its
   runs leave the window (earlier_view).
6. A paused or archived job (or one of an archived client) is suppressed:
   its open occurrences are removed, nothing else changes and no flip is
   made. When it comes back, occurrences start again at that moment, so the
   time it was away never counts as missed.
"""

import bisect
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Final

from app.evaluator.model import (
    CLOSED_STATES,
    OPEN_STATES,
    AttributionBasis,
    Evaluation,
    FlipDraft,
    JobRules,
    JobState,
    MaintenanceWindow,
    Occurrence,
    OccurrenceState,
    Result,
    StateRecord,
)
from app.ingest.results import ResultStatus
from app.schedule import deadline, next_n, occurrences

# Occurrences are kept and evaluated for this long (lazy, rnd-report-2 5.5).
WINDOW: Final = timedelta(days=14)
# A result belongs to the latest occurrence at or before its basis time plus
# this much.
ATTRIBUTION_SLACK: Final = timedelta(minutes=10)
# Occurrences are written this far ahead of their time, so a run that starts
# or reports up to ATTRIBUTION_SLACK early finds its occurrence.
LOOKAHEAD: Final = ATTRIBUTION_SLACK
FINAL_STATUSES: Final[frozenset[ResultStatus]] = frozenset(
    {"success", "warning", "failed"}
)
FAILURE_STATES: Final[frozenset[OccurrenceState]] = frozenset({"failed", "missed"})
NOTE_LENGTH: Final = 200
REASON_LENGTH: Final = 300
_INSTANT: Final = timedelta(microseconds=1)


def _clip(text: str | None, length: int) -> str | None:
    if text is None:
        return None
    return text if len(text) <= length else text[: length - 1] + "…"


def _when(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def window_start(job: JobRules, now: datetime) -> datetime:
    """The oldest scheduled time the evaluator still looks at for this job."""
    minutes = job.max_runtime_minutes + job.grace_minutes + job.escalate_minutes
    span = timedelta(minutes=minutes) + timedelta(days=1)
    return now - max(WINDOW, span)


def first_time(job: JobRules, record: StateRecord, now: datetime) -> datetime:
    """Where the job's occurrences start: within the window, not before the
    job was created, not before the end of its last pause or archive."""
    start = max(window_start(job, now), job.created_at)
    if record.eval_from is not None:
        start = max(start, record.eval_from)
    return start


def earlier_view(
    occurrences: Iterable[Occurrence], start: datetime, threshold: int
) -> list[Occurrence]:
    """The closed occurrences due before start that the job state still
    depends on, oldest first: the newest one (the state when the window has
    none) and the newest threshold that are not maintenance (enough to tell
    whether a run of failures reaches the threshold; maintenance neither
    counts nor breaks a run)."""
    by_time = {
        item.scheduled_for: item
        for item in occurrences
        if item.scheduled_for < start and item.state in CLOSED_STATES
    }
    if not by_time:
        return []
    closed = [by_time[moment] for moment in sorted(by_time)]
    counted = [item for item in closed if item.state != "maintenance"]
    kept = {item.scheduled_for: item for item in counted[-max(threshold, 1) :]}
    kept[closed[-1].scheduled_for] = closed[-1]
    return [kept[moment] for moment in sorted(kept)]


def expected_times(job: JobRules, start: datetime, now: datetime) -> list[datetime]:
    """The job's scheduled times t with start <= t <= now + LOOKAHEAD."""
    return occurrences(job.spec, start, now + LOOKAHEAD + _INSTANT)


def attribute(
    times: Sequence[datetime], results: Iterable[Result], basis: AttributionBasis
) -> dict[datetime, list[Result]]:
    """Each result to the latest of the sorted times at or before its basis
    time plus ATTRIBUTION_SLACK; a result before the first time belongs to
    none."""
    found: dict[datetime, list[Result]] = {}
    for result in results:
        moment = result.basis(basis) + ATTRIBUTION_SLACK
        index = bisect.bisect_right(times, moment) - 1
        if index >= 0:
            found.setdefault(times[index], []).append(result)
    return found


@dataclass(frozen=True, slots=True)
class Outcome:
    """The state of one occurrence, the result that decided it and a note."""

    state: OccurrenceState
    result: Result | None = None
    note: str | None = None


def _final(job: JobRules, due: datetime, finals: Sequence[Result]) -> Outcome:
    """The outcome decided by the latest final result (finals sorted)."""
    latest = finals[-1]
    notes: list[str] = []
    state: OccurrenceState
    if latest.status == "success":
        state = "verified"
        if any(result.status == "failed" for result in finals[:-1]):
            notes.append("recovered after retry")
    elif latest.status == "warning":
        if job.warning_policy == "warning_counts_ok":
            state = "verified"
            notes.append("warning counted as success")
        else:
            state = "warning"
    else:
        state = "failed"
    if latest.basis(job.attribution_basis) >= due + job.escalation:
        notes.append("late result")
    return Outcome(state, latest, "; ".join(notes) or None)


def occurrence_outcome(
    job: JobRules,
    scheduled_for: datetime,
    results: Sequence[Result],
    now: datetime,
    windows: Sequence[MaintenanceWindow] = (),
) -> Outcome:
    """The state of the occurrence due at scheduled_for, given the results
    attributed to it, at time now."""
    due = deadline(scheduled_for, job.max_runtime_minutes, job.grace_minutes)

    def order(result: Result) -> tuple[datetime, datetime, str]:
        return (result.basis(job.attribution_basis), result.received_at, str(result.id))

    finals = sorted(
        (result for result in results if result.status in FINAL_STATUSES), key=order
    )
    if any(window.covers(scheduled_for) for window in windows):
        latest = finals[-1] if finals else None
        return Outcome("maintenance", latest, "maintenance window")
    if finals:
        return _final(job, due, finals)
    starts = sorted(
        (result for result in results if result.status == "started"), key=order
    )
    start = starts[-1] if starts else None
    ignored = (
        "unknown result ignored"
        if any(result.status == "unknown" for result in results)
        else None
    )
    if now < due:
        return Outcome("pending" if start is None else "running", start, ignored)
    note = ignored if start is None else "started, never finished"
    if now < due + job.escalation:
        return Outcome("overdue", start, note)
    return Outcome("missed", start, note)


@dataclass(frozen=True, slots=True)
class Derived:
    """The job state, the consecutive failed or missed occurrences and the
    newest closed occurrence it derives from."""

    state: JobState
    failures: int
    newest: Occurrence | None


def derive_state(
    history: Sequence[Occurrence], now: datetime, threshold: int
) -> Derived:
    """The job state from its occurrences (sorted by scheduled_for)."""
    closed = [
        item
        for item in history
        if item.scheduled_for <= now and item.state in CLOSED_STATES
    ]
    if not closed:
        return Derived("unknown", 0, None)
    newest = closed[-1]
    failures = 0
    for item in reversed(closed):
        if item.state in FAILURE_STATES:
            failures += 1
        elif item.state != "maintenance":
            break
    state: JobState
    if newest.state == "verified":
        state = "ok"
    elif newest.state == "warning":
        state = "warning"
    elif newest.state == "maintenance":
        state = "maintenance"
    elif failures >= threshold:
        state = "missed" if newest.state == "missed" else "failing"
    else:
        state = "warning"
    return Derived(state, failures, newest)


def flip_reason(before: JobState, derived: Derived, threshold: int) -> str:
    """Why the job state changed, in one sentence for notifications."""
    newest = derived.newest
    if newest is None:
        return "No run has an outcome yet"
    run = f"run due {_when(newest.scheduled_for)}"
    if derived.state == "ok" and before in ("failing", "missed"):
        text = f"Recovered: the {run} was verified"
    elif derived.state == "ok":
        text = f"The {run} was verified"
    elif derived.state == "maintenance":
        text = f"The {run} was in a maintenance window"
    elif newest.state == "warning":
        text = f"The {run} ended with a warning"
    else:
        verb = "was missed" if newest.state == "missed" else "failed"
        text = f"The {run} {verb}"
        if derived.state == "warning":
            text += f"; {derived.failures} of {threshold} failures before an alert"
        elif derived.failures > 1:
            text += f"; {derived.failures} in a row"
    if newest.note and newest.state != "maintenance":
        text += f" ({newest.note})"
    return _clip(text, REASON_LENGTH) or text


def next_due(
    job: JobRules, current: Iterable[Occurrence], now: datetime
) -> datetime | None:
    """The next moment time alone changes the job: a deadline of a pending or
    running occurrence, the escalation of an overdue one, or the moment the
    next scheduled time must be written."""
    moments: list[datetime] = []
    for item in current:
        if item.state in ("pending", "running") and item.deadline > now:
            moments.append(item.deadline)
        elif item.state == "overdue":
            moments.append(item.deadline + job.escalation)
    upcoming = next_n(job.spec, now + LOOKAHEAD, 1)
    moments.extend(moment - LOOKAHEAD for moment in upcoming)
    return min(moments, default=None)


def _suppress(before: StateRecord, stored: Sequence[Occurrence]) -> Evaluation:
    """A paused or archived job: open occurrences go, the state stays."""
    deletes = tuple(item for item in stored if item.state in OPEN_STATES)
    return Evaluation(
        inserts=(),
        updates=(),
        deletes=deletes,
        record=replace(before, suppressed=True),
        flip=None,
        due_at=None,
    )


def evaluate(
    job: JobRules,
    record: StateRecord | None,
    stored: Sequence[Occurrence],
    results: Sequence[Result],
    now: datetime,
    *,
    suppressed: bool = False,
    windows: Sequence[MaintenanceWindow] = (),
    earlier: Sequence[Occurrence] = (),
) -> Evaluation:
    """Evaluate one job at time now.

    record is what job_state holds (None before the first evaluation), stored
    the job's occurrences, results its bound results; windows the job's
    maintenance windows. earlier holds stored occurrences due before stored
    (the worker reads only the newest of them; at least earlier_view's).
    Stored occurrences older than the window are left alone; the closed ones
    of earlier_view still decide the job state.
    """
    before = record or StateRecord()
    start = window_start(job, now)
    threshold = job.consecutive_failures_to_alert
    older = earlier_view([*earlier, *stored], start, threshold)
    stored = [item for item in stored if item.scheduled_for >= start]
    if suppressed:
        return _suppress(before, stored)
    # Back from a pause or an archive: the time away never counts.
    eval_from = now if before.suppressed else before.eval_from
    current = replace(before, eval_from=eval_from, suppressed=False)
    times = expected_times(job, first_time(job, current, now), now)
    attributed = attribute(times, results, job.attribution_basis)
    computed: dict[datetime, Occurrence] = {}
    ended: list[datetime] = []
    for moment in times:
        outcome = occurrence_outcome(
            job, moment, attributed.get(moment, []), now, windows
        )
        computed[moment] = Occurrence(
            scheduled_for=moment,
            deadline=deadline(moment, job.max_runtime_minutes, job.grace_minutes),
            state=outcome.state,
            result_id=None if outcome.result is None else outcome.result.id,
            note=_clip(outcome.note, NOTE_LENGTH),
        )
        if outcome.state == "verified" and outcome.result is not None:
            ended.append(outcome.result.ended_at)
    by_time: Mapping[datetime, Occurrence] = {
        item.scheduled_for: item for item in stored
    }
    inserts = tuple(item for moment, item in computed.items() if moment not in by_time)
    updates = tuple(
        (by_time[moment], item)
        for moment, item in computed.items()
        if moment in by_time and by_time[moment] != item
    )
    # A stored occurrence the schedule no longer has (changed schedule, time
    # away): open ones go, closed ones stay as history.
    gone = [item for item in stored if item.scheduled_for not in computed]
    deletes = tuple(item for item in gone if item.state in OPEN_STATES)
    kept = [item for item in gone if item.state not in OPEN_STATES]
    history = sorted(
        [*older, *computed.values(), *kept], key=lambda item: item.scheduled_for
    )
    derived = derive_state(history, now, threshold)
    if before.last_success_at is not None:
        ended.append(before.last_success_at)
    changed = derived.state != before.state
    flip: FlipDraft | None = None
    if changed:
        newest = derived.newest
        flip = FlipDraft(
            from_state=before.state,
            to_state=derived.state,
            reason=flip_reason(before.state, derived, threshold),
            scheduled_for=None if newest is None else newest.scheduled_for,
        )
    after = StateRecord(
        state=derived.state,
        since=now if changed or record is None else before.since,
        consecutive_failures=derived.failures,
        last_success_at=max(ended, default=None),
        eval_from=eval_from,
        suppressed=False,
    )
    return Evaluation(
        inserts=inserts,
        updates=updates,
        deletes=deletes,
        record=after,
        flip=flip,
        due_at=next_due(job, computed.values(), now),
    )
