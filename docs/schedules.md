# Job schedules

A job says when it should report: a schedule kind, an expression and an IANA time zone. The library is `app/schedule/` (pure code, no I/O); `POST /api/v1/schedule/preview` shows the next times while a job is edited, and saving a job checks the schedule with the same rules.

## Kinds

| Kind | Expression | Examples |
| --- | --- | --- |
| `daily` | One or more local times `HH:MM`, separated by commas | `23:00`, `06:00, 18:00` |
| `cron` | Five fields: minute, hour, day of month, month, day of week; or `@hourly`, `@daily`, `@midnight`, `@weekly`, `@monthly`, `@yearly`, `@annually` | `0 22 * * 1-5`, `30 1 * * *`, `*/15 * * * *` |
| `interval` | Elapsed time with `d`, `h` and `m`, from 1 minute to 366 days | `30m`, `6h`, `1h30m`, `1d` |

- Cron and daily times are read in the job's time zone. Day of month and day of week combine by OR when both are restricted (croniter's rule). Seconds, years and the hashed (`H`) and random (`R`) values are refused.
- An interval counts real elapsed time from the job's creation; the first expected run is one interval after it. Clocks changing for daylight saving do not move it, so its local time shifts by an hour twice a year.
- A schedule that never fires in the next ten years (for example 30 February) is refused.
- Saved expressions are normalised: `daily` times sorted and unique, cron fields separated by single spaces, macros written out (`@daily` becomes `0 0 * * *`), intervals in lower case without spaces.

## Daylight saving (rnd-report-2 5.5)

| Case | Rule | Europe/Lisbon example |
| --- | --- | --- |
| The local time does not exist (spring gap) | Fires once, at the first valid instant after the gap | 01:30 on 28 March 2027 fires at 02:00 WEST |
| The local time exists twice (autumn repeat) | Fires once, at the first of the two | 01:30 on 31 October 2027 fires at 01:30 WEST, not again at 01:30 WET |
| Cron with an hour of `*` or `*/n` | Every real hour counts, so both instances of the repeated hour fire | `0 * * * *` fires at 01:00 WEST and 01:00 WET |

An hour range such as `0-23` counts as a fixed hour (docs/spikes.md). The rule depends only on the wall time and the zone, so a restart or a different query window never changes the times. croniter is only asked which wall-clock times match an expression (`app/schedule/_cron.py`); turning them into instants is `app/schedule/_wall.py`.

## Next times

`next_n` (the preview and the check on save) walks the wall-clock times from the given moment and stops once the n-th time is settled, so its cost grows with n and not with how dense the schedule is: `* * * 1-3 *` asked in November costs about as much as a daily job. It looks ten years ahead (`NEXT_HORIZON`). `occurrences` lists a whole window and refuses one with more than 100000 times.

## Deadline

An occurrence without a final result is overdue at `scheduled time + max_runtime_minutes + grace_minutes` (`deadline`), and missed after `escalate_minutes` more (evaluator, phase C7).

## Tests

- `tests/schedule/golden/`: expected times for Europe/Lisbon, Europe/London, America/New_York and UTC across both 2027 changes, leap days, interval anchors, `next_n` and invalid input. Each case lists UTC times and the same times with their local offset.
- `tests/schedule/reference.py`: a minute-by-minute second implementation; the property tests compare the library with it and check that times are monotonic, unique and independent of the query window.
