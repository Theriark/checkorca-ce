# Backend spikes (phase C0-B)

Six checks of the libraries and PostgreSQL features that later phases build on. They live in `tests/spikes/` and run in every merge gate (check 2, pytest on PostgreSQL 16), so a dependency update that breaks one fails CI. Every spike prints a `spike <name>: ...` line with its measurements in the pytest log.

**Result: all six pass. No fallback is needed:** asyncpg, aiosmtpd and croniter stay. The plan's fallbacks remain documented in `docs/licences.md`: pg8000 in a thread pool for asyncpg, an own SMTP receiver for aiosmtpd and an own cron parser for croniter.

Measured in CI run 44305216358 (GitHub-hosted ubuntu-latest, Python 3.12.16, PostgreSQL 16.15 service container, commit 41c8116). The timings come from one run on a shared runner, so read them as orders of magnitude, not benchmarks.

## Results

| # | Spike | Test file | Versions | Result | Timing |
| --- | --- | --- | --- | --- | --- |
| 1 | Advisory lock: of two sessions one holds the fixed `pg_advisory_lock` key; the second gets it after the first unlocks, and when the first session ends without unlocking | `test_spike_advisory_lock.py` | asyncpg 0.32.0, SQLAlchemy 2.1.9, PostgreSQL 16.15 | pass | handover after unlock 1.4 ms; takeover after the holder's session ended 0.5 ms |
| 2 | `SELECT ... FOR UPDATE SKIP LOCKED`: two sessions claim disjoint batches (1-4 and 5-8; after a rollback the first gets 1-4 and 9-12); 4 concurrent workers drain 40 rows, each row exactly once | `test_spike_skip_locked.py` | as above | pass | 40 rows in 137.2 ms, 10 rows per worker |
| 3 | Alembic upgrade head, check, downgrade -1, upgrade head through asyncpg, with the configuration of `python -m app migrate` (async `migrations/env.py`, migration lock, `c0_baseline`) | `test_spike_alembic.py` | Alembic 1.20.1, asyncpg 0.32.0, server_version_num 160015 | pass | full cycle 174.6 ms |
| 4 | regex timeout: a runaway pattern is stopped by `timeout=0.05` three times in a row and the process keeps matching | `test_spike_regex_timeout.py` | regex 2026.11.18 | pass | stopped after 52.3, 50.5 and 50.5 ms |
| 5 | aiosmtpd receives one synthetic message on Python 3.12: threaded `Controller` on a free port, and an `SMTP` server on the running event loop | `test_spike_aiosmtpd.py` | aiosmtpd 1.4.6, Python 3.12.16 | pass | send and receive 6.5 ms (Controller), 4.2 ms (event loop) |
| 6 | croniter with `zoneinfo`: Europe/Lisbon next fire times across both 2027 DST changes | `test_spike_croniter.py` | croniter 7.0.0 | pass, with one finding (below) | about 14 ms for the four croniter tests together |

## Notes per spike

**1. Advisory lock.** The C4-B worker should take the session-level lock (`pg_advisory_lock`, or `pg_try_advisory_lock` in its tick) on a dedicated connection that it keeps open. The server frees the key as soon as that session ends, so a crashed worker never leaves a stale lock. The spike uses key 4_270_901; migrations use 4_270_001 (`migrations/env.py`). C4-B picks its own fixed key in that range and records it next to the migration key.

**2. SKIP LOCKED.** A claim is `SELECT id ... WHERE <pending> ORDER BY id LIMIT n FOR UPDATE SKIP LOCKED` followed by the update in the same transaction. Rows whose transaction rolls back become claimable again. The spike's table is in its own schema (`spike_c0b`), dropped after each test, so `alembic check` never sees it.

**3. Alembic on asyncpg.** `env.py` runs the migration through `AsyncConnection.run_sync` under `pg_advisory_xact_lock`. `alembic check` reports no difference between the models and `c0_baseline`. The command-line form of the same cycle stays merge gate check 3.

**4. regex timeout.** `^(11+?)\1+$` on a subject of 1,000,003 characters (a prime length) needs about n² steps, and the backreference leaves nothing to memoise. Only the timeout stops it, and `TimeoutError` arrives about 0.5 to 2.5 ms after the 50 ms limit. The textbook `^(a+)+$` on `"a" * 40 + "!"` is not catastrophic in this engine: it answers "no match" in under 0.1 ms. The C5-I parser engine passes `timeout=0.05` on every pack pattern and treats `TimeoutError` as a parse error for that message, never as a status.

**5. aiosmtpd 1.4.6.** It works unchanged on Python 3.12. C4-I can start `SMTP(handler, hostname=...)` with `loop.create_server` inside the worker's event loop; the threaded `Controller` is not needed. STARTTLS, the size limit and the per-source rate limits are C4-I's tests, not part of this spike.

**6. croniter with zoneinfo.** Results with an aware start time in `ZoneInfo("Europe/Lisbon")`:

| Case | croniter 7.0.0 gives | Correct? |
| --- | --- | --- |
| Daily 23:00, spring change (28 Mar) | 23:00 WET, 23:00 WET, 23:00 WEST, 23:00 WEST | yes, local wall time kept |
| Daily 23:00, autumn change (31 Oct) | 23:00 WEST, 23:00 WEST, 23:00 WET, 23:00 WET | yes |
| Hourly through the spring gap | 00:00 WET, 02:00 WEST, 03:00 WEST, 04:00 WEST (consecutive UTC hours) | yes |
| Hourly through the repeated hour | 00:00 WEST, 01:00 WEST, 01:00 WET, 02:00 WET (consecutive UTC hours) | yes |
| Daily 01:30 on the gap day (01:30 does not exist) | once, at 02:00 WEST (01:00Z) | acceptable: fires once, at the end of the gap |
| Daily 01:30 on the repeated-hour day | **twice**: 01:30 WEST (00:30Z) and 01:30 WET (01:30Z) | no: a daily job must fire once |

**Finding for C3-B.** croniter stays; this is not a reason to use the fallback. `app/schedule/_cron.py` must drop the second fire of a wall time that falls in the repeated hour. For an expression with a fixed hour, keep only the first instance (fold 0) of each local date and time. Hourly and minute schedules keep both instances, because each one is a real hour. For the gap case, the DST policy of rnd-report-2 5.5 decides whether 02:00 WEST is right or whether to shift by the gap length (02:30 WEST). The tests pin both observed cases, so a croniter upgrade that changes them fails CI (legal L-2), and C3-B's golden tables in `tests/schedule/golden` take over from there.

## Fallback decisions

| Library | Planned fallback | Decision |
| --- | --- | --- |
| asyncpg 0.32.0 | pg8000 in a thread pool | not needed |
| aiosmtpd 1.4.6 | own small SMTP receiver | not needed |
| croniter 7.0.0 | own five-field cron parser behind `_cron.py` | not needed; `_cron.py` adds the repeated-hour rule above |
| regex 2026.11.18 | none planned | not needed |
