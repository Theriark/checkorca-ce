# Evaluator

The evaluator turns a job's schedule and its results into expected runs (occurrences), a job state and flips (phase C7, rnd-report-2 5.5). The rules are pure code in `app/evaluator/machine.py` (no clock, no database); `app/evaluator/tick.py` runs them in the worker on every tick (`TICK_HOOKS` in `app/worker/loop.py`, after the parse hook, so a result parsed in a tick counts in the same tick).

## Occurrences

- Written lazily for the last 14 days and up to 10 minutes ahead, from the job's schedule (`app/schedule`, with its daylight-saving rules in [schedules.md](schedules.md)). Never before the job was created, and never for the time a job was paused or archived (see Pause and archive). A job whose max runtime, grace and escalation add up to more than 13 days looks back that long plus one day, so its runs can still close.
- Deadline = scheduled time + `max_runtime_minutes` + `grace_minutes` (elapsed time, so a night with a clock change has the same deadline length).
- A result belongs to the latest occurrence at or before its basis time plus 10 minutes. The basis is the job's `attribution_basis`: `started`, `finished` (default) or `received`; when the result lacks that time, its receipt time. A result before the job's first occurrence stays in history only.

| State | When |
| --- | --- |
| `pending` | No final result and the deadline has not passed (also before the scheduled time) |
| `running` | A start (ping `/start` or a `started` result) without a final result, before the deadline |
| `verified` | The latest final result is a success, or a warning under `warning_counts_ok` |
| `warning` | The latest final result is a warning under `warning_is_attention` (default) |
| `failed` | The latest final result is a failure |
| `overdue` | No final result, deadline passed, escalation not yet: silent, warning level |
| `missed` | No final result at deadline + `escalate_minutes` (a start that never finished too) |
| `maintenance` | The SuppressionProvider puts the scheduled time in a maintenance window |

Silent means overdue or missed. Final results are success, warning and failed; the latest by basis time wins, so failed then success is verified with the note `recovered after retry`, and success then failed is failed. A final result after the missed point adds the note `late result`. `unknown` results never verify anything (note `unknown result ignored`). An occurrence's `result_id` is the result that decided it (or the start of a running one).

## Job state and flips

The job state derives from the newest closed occurrence (verified, warning, failed, missed, maintenance) that is due:

| Newest closed occurrence | Job state |
| --- | --- |
| none yet | `unknown` |
| verified | `ok` |
| warning | `warning` |
| maintenance | `maintenance` |
| failed or missed, fewer than `consecutive_failures_to_alert` in a row | `warning` (reason names the count, for example 1 of 3) |
| failed or missed, threshold reached | `failing`, or `missed` when the newest is missed |

Maintenance occurrences neither count as failures nor break a run of them. The API shows `paused` while a job is paused (from the job itself). `state_since` is when the state last changed and `last_success_at` when the newest verified run ended.

The state looks past the 14-day window: besides the window's occurrences it reads the newest closed occurrence before it and the newest `consecutive_failures_to_alert` closed ones that are not maintenance. So a monthly job stays `ok` for the whole month after a verified run, and a weekly job with a threshold of 3 (or a daily one with 20) reaches it although its first failures have left the window. The count of failures in a row (in flip reasons) covers the window plus at most `consecutive_failures_to_alert` runs before it; a longer run of failures shows that many.

Each change of the job state inserts one flip (`from_state`, `to_state`, `reason`, `at`, the job and its client; the row also keeps the occurrence that caused it). Flips are the single source of alerts (phase C9): a flip to `failing` or `missed` happens once, when the threshold is reached; a flip to `ok` from `failing` or `missed` is the recovery (reason starts with `Recovered:`). A late success after a missed run turns the occurrence into verified and gives exactly one recovery flip.

Property, checked by `tests/evaluator`: job state `ok` means the newest closed occurrence is verified.

## Pause and archive

A paused job, an archived job and the jobs of an archived client are suppressed: their open occurrences (pending, running, overdue) are removed, closed ones stay as history, the job state stays and no flip is made. When the job comes back, occurrences start at that moment, so the time away never counts as missed and never alerts.

## Every tick, bounded and idempotent

One query reads every job with its job_state row and the count and newest time of its results of the last 30 days. A job is evaluated only when something can have changed: no job_state row yet; paused, archived or resumed; settings changed (`updated_at`); a result arrived or was bound (count or newest time changed); its due time passed (a deadline, an escalation, or the next occurrence to write); or it was last evaluated an hour ago. A tick evaluates at most 2000 jobs, due first, in transactions of 200, and starts no new batch after 20 seconds; the rest wait for the next tick. Evaluating twice at the same time changes nothing: the second tick finds nothing due, and an evaluation from the same rows writes no change.

Each batch first claims its jobs in its transaction: the clients and the jobs `FOR KEY SHARE` and the job_state rows `FOR UPDATE`, all `SKIP LOCKED`, so the evaluator never waits for a lock. A job is left for the next tick when it is gone, when its client or job row is locked (a client delete or a job change in progress), or when its job_state row is locked or changed since the tick read it (a second worker after a lost worker lock evaluated it), so no flip is made twice. A client delete that starts while a batch holds the client's rows waits for the batch and then deletes its rows too.

A batch that fails (a conflicting change, a SuppressionProvider error) is rolled back and evaluated on the next tick. A job whose stored schedule no longer parses is skipped, logged and tried again an hour later. 100 clients with 4 jobs over 14 days (5,600 occurrences) evaluate in under 2 seconds (`tests/evaluator/test_tick.py`).

## Extension seams (app/ext)

- `SuppressionProvider.maintenance(targets, start, end)` gives each job's maintenance windows; CE ships `NoSuppression` (nothing suppressed). EE adds maintenance windows.
- `EventSubscriber.handle(event)` receives `OccurrenceChanged` (job_id, scheduled_for, old_state, new_state, at; old_state is null for a new occurrence and new_state null for a removed one) and `FlipCreated` (flip_id, job_id, client_id, from_state, to_state, reason, at) after the evaluator's commit, inside the worker. `NotificationSent` (notification_id, flip_id, channel_id, status) is defined now and raised from phase C9. A subscriber that raises or takes longer than 10 seconds is logged with its name and the event type and never stops the tick. CE ships no subscriber; `WorkerContext.subscribers` holds them.

## API

- `GET /api/v1/jobs/{id}/occurrences?from=&to=` (default the last 14 days to 24 hours ahead; cursor and limit): occurrences oldest first with `job_id`, `scheduled_for`, `deadline`, `state`, `result_id`, `note`. Times after the evaluator's last tick are listed as `pending` from the schedule (not stored yet); a paused or archived job lists none of those.
- `GET /api/v1/flips?job_id=&client_id=&since=` (cursor and limit): flips newest first with `id`, `job_id`, `client_id`, `from_state`, `to_state`, `reason`, `at`.
- Jobs show `state`, `state_since` and `last_success_at` from the evaluator; `GET /jobs?state=` filters by it and clients count their jobs by it.

## Data

Tables `occurrence` (key job_id and scheduled_for), `job_state` (one row per job) and `flip` (revision `c7_eval`). All three are in the client delete map, which locks the client's jobs before its steps; deleting a result sets `occurrence.result_id` to null and the next evaluation decides again. Closed occurrences stay as history; a retention purge (phase C10) must keep each job's newest closed occurrence and its newest `consecutive_failures_to_alert` closed ones that are not maintenance, which the job state still reads.
