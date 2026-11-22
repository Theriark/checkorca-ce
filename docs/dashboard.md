# Dashboard, exports and the morning digest

Phase C8-B adds what the Morning check (phase C8-F) reads: `dashboard/today`, `dashboard/ribbon`, `dashboard/trend`, `dashboard/breakdown`, `activity`, `jobs/{id}/acknowledge`, the full `system/status`, three CSV exports and `digest/preview`. Every route is under `/api/v1`, answers problem documents on errors and takes a signed-in session or an API token of scope `read` (acknowledge is a state change: session and `X-CSRF-Token`). Times are ISO 8601 UTC with `Z`. The routes live in `app/api/v1/dashboard.py` and `app/api/v1/exports.py`, the queries in `app/repos/dashboard.py`; each route runs a fixed number of queries whatever the number of clients and jobs (`tests/api/test_dashboard_api.py` counts them).

## Words

- **Due run**: an occurrence ([evaluator.md](evaluator.md)) whose outcome is known or late: `verified`, `warning`, `failed`, `overdue` or `missed`. `pending` and `running` are still waiting; `maintenance` counts nowhere.
- **Silent**: overdue or missed. Overdue is late but not yet escalated; missed is escalated.
- **Live job**: a job that is not archived, of a client that is not archived. The dashboard, the ribbon, the trend, the breakdown and the digest count live jobs only. The exports keep archived jobs and clients: history is history.
- **Digest zone**: `settings.digest_timezone` (default Europe/Lisbon). Calendar days (trend, breakdown, day export, digest) and the night of the ribbon are local to it; every bound is a UTC instant. The hour skipped when summer time starts is read with the offset before the change, so a day is 23 or 25 hours across a clock change.

## dashboard/today

| Field | Meaning |
| --- | --- |
| `stats.verified`, `stats.failed`, `stats.silent` | Due runs of live jobs whose scheduled time is in the 24 hours up to now (`(now - 24 h, now]`), by state. |
| `stats.unmatched` | Results waiting in Unmatched now (no job bound). |
| `stats.paused` | Live jobs paused now (until resumed or until a time). |
| `value` | The number for the 24 hours up to now. |
| `delta_vs_yesterday` | `value` minus the number of the 24 hours before. |
| `spark14` | 14 numbers, one per 24 hours, oldest first; the last one is `value`. |
| `coverage` | Due runs of the last 24 hours: `verified` of `expected` (verified + warning + failed + silent); `ratio` = verified / expected rounded to 4 places, `null` when nothing was due. |
| `attention` | Live jobs that are not paused and need a look (below). |
| `heartbeat` | The worker heartbeat: `at`, `age_seconds`, `stale` (older than 3 minutes or missing). |
| `demo_seeded` | The demo data was seeded (`settings.demo_seeded`). |

Two numbers have no full history, so their sparkline is an approximation:

- `unmatched`: the value of an earlier day is the results waiting now less those that arrived later; a result assigned since then is not counted on the earlier days.
- `paused`: pauses keep no history, so `spark14` repeats today's value and `delta_vs_yesterday` is 0.

### Needs attention

A live job that is not paused is listed when its job state is `missed`, `failing` or `warning`, or when its newest due run is `overdue`. `state` is the run's word: `missed`, `overdue`, `failed` (job state `failing`) or `warning`. Order: silent (missed and overdue) first, then failed, then warning; within each group the jobs nobody acknowledged first, then the oldest `expected_by`, then client and job name.

- `expected_by`: the deadline of the newest due run.
- `last_success_at`: when the job last ended well (from the evaluator).
- `raw_message_id`: the message of the result that decided the newest due run; `null` for a silent run, a ping or the results API.
- `acknowledged_at` (addition): set by `POST jobs/{id}/acknowledge`, `null` otherwise.

## jobs/{id}/acknowledge

`POST`, session with `X-CSRF-Token`. Sets the job's `acknowledged_by` (the user) and `acknowledged_at` (now), audits `job.acknowledge`, answers the job (`JobOut`). `updated_at` stays: the settings did not change. The next flip of the job state clears both (in the evaluator's write, `app/repos/evaluation.py`), so a new state needs a look again. 404 for an unknown job.

## dashboard/ribbon

Query: `from`, `to` (aware times), `problems_only` (default false). Without `from` and `to` the window is the night in the digest zone: 18:00 to 12:00, the night that ended or ends today before 18:00, tonight's from 18:00 on. One bound alone gives an 18-hour window; `to` must be later than `from` and the window at most 72 hours (422 otherwise).

`window` (`from`, `to`), `morning_line_at` (the digest time inside the window, `null` when there is none), `clients` by name, each with its live jobs by name, each with its `occurrences` due in `[from, to)` by time: `scheduled_for`, `deadline`, `state` (the occurrence states of [evaluator.md](evaluator.md)), `result_at` (when the deciding result says the run ended: finished, else received; `null` without a result). Runs after now that the evaluator has not written yet are listed as `pending` from the job's schedule (none for a paused job). Clients and jobs without a run in the window are left out. `problems_only` keeps the jobs with a `warning`, `failed`, `overdue` or `missed` run in the window. A hollow ring in the Night Ribbon is an `overdue` or `missed` run.

## dashboard/trend and dashboard/breakdown

Query: `days` (1 to 90, default 30): calendar days in the digest zone, ending today (today so far is the last day).

- `trend`: `items`, one per day, oldest first: `date`, `verified`, `failed`, `silent` (due runs of live jobs scheduled that day).
- `breakdown`: `by` = `vendor` (default) or `client`; `items` by label: `key`, `label`, `verified`, `failed`, `silent` over the same days. For `vendor` the key is the job's parser pack id and the label the pack's vendor; jobs without a parser pack (pings and the results API) share the key `none`. For `client` the key is the client id and the label its name. The vendor is the pack set on the job (`parser_pack_id`), not the pack that parsed each mail.

## activity

Cursor list (`cursor`, `limit` 50, at most 200), newest first; `kind` narrows it to one kind. Items: `id` (addition: a stable key), `at`, `kind`, `summary`, `ref_kind`, `ref_id`.

| Kind | Source | summary | ref |
| --- | --- | --- | --- |
| `ingest` | a received message | `Message received in <inbox label>: <parse state>` | `message`, message id |
| `flip` | a change of job state | `<job> (<client>): <from> to <to>` | `job`, job id |
| `config` | an audit event of `client.`, `job.`, `inbox.`, `pack.`, `unmatched.`, `token.` or `user.` | the action in words, for example `Job pause` | the audited target |
| `notification` | phase C9 | | |

Sign-ins and the seed are not activity.

## system/status

Adds to phase C4: `queue.pending_notifications` and `queue.failed_notifications` (0 until phase C9 sends notifications), `evaluator_lag_seconds` (how long the oldest evaluation the evaluator owes has waited: a due time it has not looked at yet, or a live job it never evaluated; 0 when it is up to date) and `extension_api_level` (1). `worker` keeps `holder` and `started_at` besides `heartbeat_at`, `age_seconds` and `stale`.

## Exports

UTF-8 with a byte order mark, CRLF line ends, a header line. A cell a spreadsheet would read as a formula (starting with `=`, `+`, `-`, `@`, tab or carriage return) starts with an apostrophe. Times are ISO 8601 UTC with `Z`; `date` is the calendar day in the digest zone. File names carry dates or the client id, never a name. No export holds a secret: no IMAP password, webhook or API token, ping token, token hash or stored credential (`tests/api/test_exports_api.py` plants canaries); a job's ping URL is left out on purpose.

### exports/day.csv and exports/history.csv

`day.csv?date=YYYY-MM-DD` (default today): every run due that day. `history.csv?from=YYYY-MM-DD&to=YYYY-MM-DD&client_id=` (days in the digest zone, both included, at most 366, default the last 30 days; `client_id` narrows to one client, 404 when unknown). One row per occurrence, by time, then client and job. At most 100 000 rows (422 beyond: choose fewer days).

| Column | Value |
| --- | --- |
| `date` | the day of `scheduled_for` in the digest zone |
| `client`, `job`, `kind`, `parser_pack_id` | the job and its client |
| `scheduled_for`, `deadline`, `state`, `note` | the occurrence |
| `result_status`, `started_at`, `finished_at`, `received_at` | the result that decided it (empty without one) |

### clients/{id}/export.csv

The full history of one client (legal D-4), one record per row, archived jobs included, oldest first within each record kind. 404 for an unknown client.

| Column | client | job | occurrence | result | flip | message |
| --- | --- | --- | --- | --- | --- | --- |
| `record` | `client` | `job` | `occurrence` | `result` | `flip` | `message` |
| `client` | name | name | name | name | name | name |
| `job` | | job | job | job (or the name in the result) | job | |
| `at` | created | created | scheduled | received | flipped | received |
| `state` | `active` or `archived` | job state | occurrence state | | | parse state |
| `status` | | | result status | result status | | |
| `scheduled_for`, `deadline` | | | yes | | | |
| `started_at`, `finished_at` | | | of the result | yes | | |
| `received_at` | | | of the result | yes | | yes |
| `from_state`, `to_state`, `reason` | | | | | yes | |
| `note` | client notes | | occurrence note | | | |
| `details` (JSON) | aliases | settings (schedule, times, policies, pause, archive, acknowledgement) | | client hint, job name, run id, message id, details | | Message-ID, subject, sender, size, parser pack and reason |

The raw message itself stays in the app (the message page shows it).

## digest/preview and the ReportRenderer

`digest/preview?date=YYYY-MM-DD` (default today; 2000 to 2099) answers `date` (addition), `subject`, `html`, `text`: the morning digest of that day as it would be sent (phase C9 sends it at `settings.digest_time_local`). The digest window is the 24 hours (digest zone) up to the digest time of that day. Counts: due runs of live jobs in the window (verified, failed, silent, warning) and coverage. Items: each job whose newest due run in the window is missed, overdue, failed or warning, silent first, then failed, then warning, at most 100 (the rest counted).

`app/notify/digest.py` builds the numbers; `DigestRenderer` (the CE `ReportRenderer` of `app/ext/reports.py`) writes them: inline-styled HTML in one table layout, no script, no image, no remote content, every client and job name and note escaped; a text body; a subject with counts and the date only (`Checkorca-CE morning check 2027-01-06: 1 failed, 1 silent, 1 warning, 1 verified`). Show the HTML in a sandboxed frame without script.

## Demo data

With `DEV_DEMO_DATA=1` on a seed host (BASE_URL host `ce-dev-*`, `ce-stg-*` or `localhost`; `python -m app` refuses to start otherwise) the worker seeds once, on its first tick while it holds the worker lock (`app/seed/demo.py`): 20 fictional clients with the note `Seed data`, 60 jobs (every CE parser pack, and scripts that report through their ping URL) and an SMTP inbox, then 14 days of history through the real pipeline on an injected clock: synthetic vendor mails (`app/seed/demo_mail.py`) through `accept_message` and the parse hook, pings through `record_result`, the evaluator every 3 simulated hours (on the demo jobs only). Some jobs never report, three stopped three days ago, five fail, four warn, eight fail now and then, one hourly script is overdue, two jobs are paused and three results wait in Unmatched. `settings.demo_seeded` becomes true; a second run adds nothing, and demo clients left by an interrupted run are not doubled. The data follows the moment it was seeded and ages from then on; phase C11-B makes the seed deterministic (D-10).
