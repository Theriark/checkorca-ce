"""The evaluator hook: on every worker tick, the jobs that need it (phase C7).

1. One query reads every job with its client's archived flag, its job_state
   row and the count and newest receipt time of its recent results.
2. A job needs an evaluation when it has no job_state row yet; when it was
   paused, archived or resumed; when its settings changed (updated_at); when
   a result arrived or was bound to it (the count or the newest time
   changed); when its due time passed (a deadline, an escalation or the next
   occurrence to write); or when it was last evaluated REFRESH ago. Nothing
   else changes an occurrence, so a tick without news writes nothing, and a
   second tick at the same time finds nothing to do (idempotent).
3. At most MAX_JOBS_PER_TICK jobs, never evaluated first, then the most
   overdue, in batches of BATCH_SIZE, and no new batch after BUDGET_SECONDS
   of the tick: each batch asks the SuppressionProvider for maintenance
   windows, then in one transaction claims its jobs (EvaluationRepository.
   claim: locks without waiting and leaves out a job that is locked, was
   deleted, changed (updated_at, client, the client's archived flag) or was
   evaluated by another worker meanwhile), reads their occurrences (and the
   newest closed ones before the window) and results, evaluates every job
   (app/evaluator/machine.py) and writes the changes. A batch that fails (a
   conflicting change, a provider error) is rolled back and evaluated again
   on the next tick.
4. After the commit, OccurrenceChanged and FlipCreated go to every
   EventSubscriber (app/ext/events.py); an error of a subscriber is logged
   and never stops the tick.
"""

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Final

from sqlalchemy.exc import IntegrityError

from app.access import SYSTEM
from app.db.models import Job, JobStateRecord
from app.evaluator.machine import LOOKAHEAD, evaluate, window_start
from app.evaluator.model import (
    Evaluation,
    JobRules,
    MaintenanceWindow,
    Occurrence,
    Result,
    StateRecord,
    as_basis,
    as_job_state,
    as_policy,
)
from app.ext.events import Event, FlipCreated, OccurrenceChanged, deliver
from app.ext.suppression import MaintenanceTarget
from app.repos.evaluation import Candidate, Changes, EvaluationRepository
from app.repos.jobs import is_paused
from app.schedule import parse_spec

if TYPE_CHECKING:
    from app.worker.loop import WorkerContext

# Jobs evaluated in one tick at most; the rest wait for the next tick.
MAX_JOBS_PER_TICK: Final = 2000
# Jobs per transaction.
BATCH_SIZE: Final = 200
# Seconds of a tick after which no new batch starts (monotonic clock).
BUDGET_SECONDS: Final = 20.0
# A job is evaluated at least this often, whatever else happens.
REFRESH: Final = timedelta(hours=1)
# Results received this long ago or later count for the change check; longer
# than the longest window (runtime, grace and escalation of 7 days each).
RESULT_SPAN: Final = timedelta(days=30)
_INSTANT: Final = timedelta(microseconds=1)
_EARLIEST: Final = datetime.min.replace(tzinfo=UTC)

logger = logging.getLogger(__name__)


def rules_of(job: Job) -> JobRules:
    """The job as the evaluator sees it; ValueError (ScheduleError) for a
    stored schedule that no longer parses."""
    return JobRules(
        id=job.id,
        client_id=job.client_id,
        spec=parse_spec(
            job.schedule_kind, job.schedule_expr, job.timezone, job.created_at
        ),
        created_at=job.created_at,
        max_runtime_minutes=job.max_runtime_minutes,
        grace_minutes=job.grace_minutes,
        escalate_minutes=job.escalate_minutes,
        attribution_basis=as_basis(job.attribution_basis),
        warning_policy=as_policy(job.warning_policy),
        consecutive_failures_to_alert=job.consecutive_failures_to_alert,
    )


def to_record(row: JobStateRecord | None) -> StateRecord | None:
    if row is None:
        return None
    return StateRecord(
        state=as_job_state(row.state),
        since=row.since,
        consecutive_failures=row.consecutive_failures,
        last_success_at=row.last_success_at,
        eval_from=row.eval_from,
        suppressed=row.suppressed,
    )


def is_suppressed(candidate: Candidate, now: datetime) -> bool:
    """Paused, archived, or of an archived client: not evaluated."""
    job = candidate.job
    return job.archived or candidate.client_archived or is_paused(job, now)


def needs_evaluation(candidate: Candidate, now: datetime) -> bool:
    """Whether anything that can change the job's occurrences happened."""
    record = candidate.record
    if record is None:
        return True
    suppressed = is_suppressed(candidate, now)
    if suppressed != record.suppressed:
        return True
    if suppressed:
        return False
    if record.job_updated_at != candidate.job.updated_at:
        return True
    seen = (record.result_count, record.result_last_at)
    if seen != (candidate.result_count, candidate.result_last_at):
        return True
    if record.due_at is not None and record.due_at <= now:
        return True
    return record.evaluated_at + REFRESH <= now


def priority(candidate: Candidate) -> tuple[int, datetime]:
    """Never evaluated first, then the longest due."""
    record = candidate.record
    if record is None:
        return (0, _EARLIEST)
    return (1, record.due_at or record.evaluated_at)


@dataclass
class TickReport:
    """What one tick did, for the log and the tests."""

    candidates: int = 0
    due: int = 0
    evaluated: int = 0
    skipped: int = 0
    rows: int = 0
    flips: int = 0
    failed_batches: int = 0
    left: int = 0
    events: int = 0
    stale: int = 0


@dataclass(frozen=True, slots=True)
class History:
    """What one batch read for its jobs, per job id: stored occurrences from
    the batch's window start, the newest closed ones before it, results and
    maintenance windows."""

    stored: Mapping[uuid.UUID, Sequence[Occurrence]]
    earlier: Mapping[uuid.UUID, Sequence[Occurrence]]
    results: Mapping[uuid.UUID, Sequence[Result]]
    windows: Mapping[uuid.UUID, Sequence[MaintenanceWindow]]


@dataclass
class Plan:
    """The rows and events of one batch, collected before the write."""

    now: datetime
    inserts: list[dict[str, Any]] = field(default_factory=list)
    updates: list[dict[str, Any]] = field(default_factory=list)
    deletes: list[tuple[uuid.UUID, datetime]] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)
    flips: list[dict[str, Any]] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    evaluated: int = 0
    # Jobs left out by the claim: locked, deleted, changed or evaluated
    # meanwhile.
    stale: int = 0

    @property
    def rows(self) -> int:
        """Occurrence rows written or deleted."""
        return len(self.inserts) + len(self.updates) + len(self.deletes)

    def changes(self) -> Changes:
        return Changes(
            inserts=self.inserts,
            updates=self.updates,
            deletes=self.deletes,
            records=self.records,
            flips=self.flips,
        )

    def _occurrence(self, job_id: uuid.UUID, item: Occurrence) -> dict[str, Any]:
        return {
            "job_id": job_id,
            "scheduled_for": item.scheduled_for,
            "deadline": item.deadline,
            "state": item.state,
            "result_id": item.result_id,
            "note": item.note,
            "evaluated_at": self.now,
        }

    def _record(
        self, candidate: Candidate, record: StateRecord, due_at: datetime | None
    ) -> dict[str, Any]:
        return {
            "job_id": candidate.job.id,
            "state": record.state,
            "since": record.since,
            "consecutive_failures": record.consecutive_failures,
            "last_success_at": record.last_success_at,
            "eval_from": record.eval_from,
            "suppressed": record.suppressed,
            "evaluated_at": self.now,
            "due_at": due_at,
            "job_updated_at": candidate.job.updated_at,
            "result_count": candidate.result_count,
            "result_last_at": candidate.result_last_at,
        }

    def skip(self, candidate: Candidate, suppressed: bool) -> None:
        """Keep the job's state; it is tried again after REFRESH (or when it
        is paused or resumed)."""
        record = to_record(candidate.record) or StateRecord()
        record = replace(record, suppressed=suppressed)
        self.records.append(self._record(candidate, record, None))

    def add(self, candidate: Candidate, evaluation: Evaluation) -> None:
        job = candidate.job
        now = self.now
        self.evaluated += 1
        for item in evaluation.inserts:
            self.inserts.append(self._occurrence(job.id, item))
            self.events.append(
                OccurrenceChanged(job.id, item.scheduled_for, None, item.state, now)
            )
        for old, new in evaluation.updates:
            self.updates.append(self._occurrence(job.id, new))
            if old.state != new.state:
                self.events.append(
                    OccurrenceChanged(
                        job.id, new.scheduled_for, old.state, new.state, now
                    )
                )
        for item in evaluation.deletes:
            self.deletes.append((job.id, item.scheduled_for))
            self.events.append(
                OccurrenceChanged(job.id, item.scheduled_for, item.state, None, now)
            )
        self.records.append(
            self._record(candidate, evaluation.record, evaluation.due_at)
        )
        flip = evaluation.flip
        if flip is None:
            return
        flip_id = uuid.uuid4()
        self.flips.append(
            {
                "id": flip_id,
                "job_id": job.id,
                "client_id": job.client_id,
                "from_state": flip.from_state,
                "to_state": flip.to_state,
                "reason": flip.reason,
                "at": now,
                "scheduled_for": flip.scheduled_for,
            }
        )
        self.events.append(
            FlipCreated(
                flip_id=flip_id,
                job_id=job.id,
                client_id=job.client_id,
                from_state=flip.from_state,
                to_state=flip.to_state,
                reason=flip.reason,
                at=now,
            )
        )


class Evaluator:
    """One tick of evaluation over the jobs that need it."""

    def __init__(
        self,
        context: "WorkerContext",
        *,
        max_jobs: int = MAX_JOBS_PER_TICK,
        batch_size: int = BATCH_SIZE,
        budget_seconds: float = BUDGET_SECONDS,
        only: frozenset[uuid.UUID] | None = None,
    ) -> None:
        """only limits the evaluation to these jobs (the demo seed replays
        its own history and leaves every other job to the worker)."""
        self.context = context
        self.max_jobs = max_jobs
        self.batch_size = batch_size
        self.budget_seconds = budget_seconds
        self.only = only

    async def run(self, now: datetime) -> TickReport:
        report = TickReport()
        async with self.context.sessionmaker() as db:
            candidates = await EvaluationRepository(db, self.context.policy).candidates(
                SYSTEM, results_since=now - RESULT_SPAN
            )
        if self.only is not None:
            candidates = [item for item in candidates if item.job.id in self.only]
        report.candidates = len(candidates)
        due = sorted(
            (item for item in candidates if needs_evaluation(item, now)), key=priority
        )
        report.due = len(due)
        chosen = due[: self.max_jobs]
        report.left = len(due) - len(chosen)
        clock = self.context.clock
        started = clock.monotonic()
        for offset in range(0, len(chosen), self.batch_size):
            if offset and clock.monotonic() - started >= self.budget_seconds:
                report.left += len(chosen) - offset
                break
            batch = chosen[offset : offset + self.batch_size]
            await self._batch(batch, now, report)
        return report

    async def _windows(
        self,
        batch: Sequence[Candidate],
        rules: Mapping[uuid.UUID, JobRules],
        now: datetime,
    ) -> Mapping[uuid.UUID, Sequence[MaintenanceWindow]]:
        targets = [
            MaintenanceTarget(item.job.id, item.job.client_id)
            for item in batch
            if item.job.id in rules and not is_suppressed(item, now)
        ]
        if not targets:
            return {}
        start = min(window_start(rules[target.job_id], now) for target in targets)
        end = now + LOOKAHEAD + _INSTANT
        return await self.context.suppression.maintenance(targets, start, end)

    async def _batch(
        self, batch: Sequence[Candidate], now: datetime, report: TickReport
    ) -> None:
        plan = Plan(now)
        rules: dict[uuid.UUID, JobRules] = {}
        for candidate in batch:
            try:
                rules[candidate.job.id] = rules_of(candidate.job)
            except ValueError:
                logger.warning(
                    "job %s has a schedule that no longer parses; not evaluated",
                    candidate.job.id,
                )
        try:
            windows = await self._windows(batch, rules, now)
        except Exception as error:
            report.failed_batches += 1
            logger.error(
                "suppression provider failed; %d jobs wait for the next tick",
                len(batch),
                exc_info=error,
            )
            return
        since = min((window_start(item, now) for item in rules.values()), default=now)
        try:
            async with self.context.sessionmaker() as db:
                repository = EvaluationRepository(db, self.context.policy)
                claimed = await repository.claim(SYSTEM, batch)
                ids = [job_id for job_id in rules if job_id in claimed]
                limit = max(
                    (rules[job_id].consecutive_failures_to_alert for job_id in ids),
                    default=1,
                )
                history = History(
                    stored=await repository.occurrences(SYSTEM, ids, since),
                    earlier=await repository.earlier(SYSTEM, ids, since, limit),
                    results=await repository.results(SYSTEM, ids, since),
                    windows=windows,
                )
                for candidate in batch:
                    if candidate.job.id in claimed:
                        self._evaluate(plan, candidate, rules, history, report)
                    else:
                        plan.stale += 1
                await repository.save(SYSTEM, plan.changes())
                await db.commit()
        except IntegrityError as error:
            report.failed_batches += 1
            logger.warning(
                "evaluator batch of %d jobs conflicted with a change made "
                "meanwhile; evaluated again next tick",
                len(batch),
                exc_info=error,
            )
            return
        report.evaluated += plan.evaluated
        report.stale += plan.stale
        report.rows += plan.rows
        report.flips += len(plan.flips)
        report.events += len(plan.events)
        await deliver(self.context.subscribers, plan.events)

    def _evaluate(
        self,
        plan: Plan,
        candidate: Candidate,
        rules: Mapping[uuid.UUID, JobRules],
        history: History,
        report: TickReport,
    ) -> None:
        job_id = candidate.job.id
        job_rules = rules.get(job_id)
        suppressed = is_suppressed(candidate, plan.now)
        if job_rules is None:
            report.skipped += 1
            plan.skip(candidate, suppressed)
            return
        try:
            evaluation = evaluate(
                job_rules,
                to_record(candidate.record),
                history.stored.get(job_id, ()),
                history.results.get(job_id, ()),
                plan.now,
                suppressed=suppressed,
                windows=history.windows.get(job_id, ()),
                earlier=history.earlier.get(job_id, ()),
            )
        except ValueError as error:
            logger.warning("job %s could not be evaluated", job_id, exc_info=error)
            report.skipped += 1
            plan.skip(candidate, suppressed)
            return
        plan.add(candidate, evaluation)


async def evaluate_jobs(context: "WorkerContext", now: datetime) -> None:
    """The tick hook (app/worker/loop.py TICK_HOOKS)."""
    report = await Evaluator(context).run(now)
    if report.evaluated or report.failed_batches or report.skipped or report.stale:
        logger.info(
            "evaluated %d of %d jobs: %d occurrence rows, %d flips, "
            "%d skipped, %d changed meanwhile, %d failed batches, "
            "%d left for the next tick",
            report.evaluated,
            report.candidates,
            report.rows,
            report.flips,
            report.skipped,
            report.stale,
            report.failed_batches,
            report.left,
        )
