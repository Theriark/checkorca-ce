# Parser packs and the parser engine

Phase C5-I (Integration and Protocol Engineer) built the pack format, the loader, the engine and the `generic-keywords` pack. C5-B (Backend Developer) added the `parser_pack` table, the matcher, the worker's parse hook, the test bench and the packs and Unmatched API (chapters below); C5-F builds the Unmatched and parser screens; C6-I the vendor packs. Source: dev-work-plan rev 35, section C5 and the Interfaces chapter (Pack YAML, ParsedResult).

## Files

| Path | Holds |
| --- | --- |
| `app/parsers/schema/pack.schema.json` | JSON Schema 2020-12 of the Pack YAML |
| `app/parsers/loader.py` | YAML text to a compiled `Pack`, or `PackInvalid` with its issues; built-in packs and their fixtures |
| `app/parsers/engine.py` | `parse`, `apply`, `mail_from_raw` and the outcomes |
| `app/parsers/model.py` | the compiled pack (`Pack`, `Condition`, `Extractor`, `StatusRule`, `FixtureRef`) |
| `app/parsers/packs/<id>.yaml` | a built-in pack; the file name is its id |
| `app/parsers/packs/fixtures/<id>/<name>.eml` and `<name>.expected.json` | the pack's sample mails and the results each must give |
| `tests/parsers/test_fixtures.py` | runs every fixture of every built-in pack |

## Pack YAML

```yaml
id: example-tool                 # ^[a-z0-9][a-z0-9._-]*$, at most 100
version: 1                       # integer, raised by one for every change
vendor: Example Tool
status: unverified-synthetic     # or verified
docs_url: https://docs.example.com/alerts   # https only; required when verified
description: optional text
match:                           # all, any or both
  all:
    - from: '@example\.com$'
  any:
    - subject: '(?i)\bbackup\b'
    - body: '(?i)job report'
split:                           # optional: digest mail
  record: '(?m)^Job: '
extract:                         # every key optional
  job_name: {regex: '^Job: (?P<name>[^\n]+)'}
  client_hint: {regex: 'for (?P<client>[^\n]+)', in: body}
  run_id: {literal: digest}
  started_at: {regex: 'Start: (?P<at>[^\n]+)', format: '%d/%m/%Y %H:%M'}
  finished_at: {regex: 'End: (?P<at>[^\n]+)'}
  details:                       # at most 16; keys ^[a-z][a-z0-9_]{0,39}$
    size: {regex: 'Size: (?P<size>[^\n]+)'}
status_rules:                    # 1 to 50, tried in order
  - {status: failed, regex: '(?i)\bfailed\b', in: subject}
  - {status: success, regex: 'Result: Success'}
fixtures:                        # at most 100
  - {name: nightly-success, origin: synthetic, class: success}
```

- A **regex** is a pattern of the `regex` module (re syntax), at most 1,000 characters, flags inline (`(?i)`, `(?m)`). YAML single quotes keep backslashes as they are.
- A **condition** has exactly one of `from`, `to`, `subject` (decoded headers) or `body` (the visible text).
- A **field** is `regex` (exactly one named group; its text is the value) or `literal`. `in` (regex only) is where the regex looks: `record` (default), `body`, `subject`, `from` or `to`. `started_at` and `finished_at` may give `format` (strptime).
- A **status rule** is `status` (`success`, `warning`, `failed`, `started`, `unknown`), `regex` and optional `in`.
- A **fixture** is `name` (^[a-z0-9][a-z0-9-]{0,79}$), `origin` (`synthetic` or `real`) and `class` (a status, `digest` for several records, or `unmatched` for mail the pack must not parse).
- `verified` needs `docs_url` and fixtures of at least 3 different classes.
- A `literal` must be plain text as a result keeps it (no control characters, line breaks, repeated or surrounding spaces). A `format` must read back what it writes for a sample time (`%d %d`, `%Q` or a stray `%` are refused). Detail keys are strings; ids, fixture names and detail keys end without a line break. No integer may reach 2**63 (YAML reads hexadecimal and binary integers of any length).

## Loading (`app/parsers/loader.py`)

```python
from app.parsers.loader import PackInvalid, builtin_packs, parse_pack

try:
    pack = parse_pack(yaml_text)
except PackInvalid as invalid:
    issues = [{"path": i.path, "message": i.message} for i in invalid.issues]
```

- At most 64 KiB of text. PyYAML's safe loader only; aliases (`*name`) are refused (a few lines of anchors and aliases expand exponentially once walked), and so are duplicate keys and nesting deeper than 10 levels, checked on the event stream before anything recursive runs. Python tags, several documents and decimal integers of more than 4,300 digits are refused as invalid YAML; any integer of 2**63 or more (hexadecimal and binary included) is refused at its path.
- Then the schema, then the checks a schema cannot express: every regex compiles, an extract regex has exactly one named group, a field gives `regex` or `literal` (and `in`/`format` only with `regex`), a literal is plain text, a format reads back, fixture names are unique, verified has 3 fixture classes.
- `PackIssue.path` is a JSON Pointer into the pack (`/status_rules/2/regex`; `""` is the whole document), `message` at most 300 characters. All issues of one pass come together, ordered by path. C5-B answers them with 422; C5-F shows each beside its line.
- `builtin_packs()` loads `app/parsers/packs/*.yaml` in file name order and refuses a file whose id is not its name. `pack_fixtures(pack)` yields the listed fixtures with their expected `ParsedResult`s.

## The engine (`app/parsers/engine.py`)

```python
from app.parsers.engine import ParseFailed, Parsed, Unmatched, mail_from_raw, parse

# app/worker/parse.py
outcome = await on_parser_thread(parse, packs, mail_from_raw(raw))
match outcome:
    case Parsed(pack_id, results):
        ...  # record_result(..., raw_message_id=message.id) for each; parse_state parsed
    case Unmatched(reason, candidates):
        ...  # parse_state unmatched; reason no-pack, tie or no-records
    case ParseFailed(pack_id, path, reason):
        ...  # parse_state error; reason timeout, deadline, too-many-records, memory
```

1. **Claim.** A pack claims the mail when every `match.all` condition and at least one `match.any` condition match. Its score is the number of matching conditions. The highest score wins; a tie between the best packs gives `Unmatched("tie", ids)`, no claim gives `Unmatched("no-pack")`. A pack whose claim times out, runs out of memory or takes more than its 1 s slice of the deadline (`CLAIM_SLICE`) is skipped for that mail: it gets no score, the outcome lists it in `skipped` as `Skipped(pack_id, path, reason)` and the other packs still compete, so one slow custom pack never fails every mail. Only the mail's own deadline running out in the claim fails the mail (`ParseFailed(..., "deadline")`). `apply(pack, mail)` skips the claim (a job's own pack). `bench(packs, mail, pack=None)` gives the test bench every pack's `Score(pack_id, matched)`, the claiming pack and the outcome (of `apply(pack)` when a pack is given, else of `parse`), on one deadline.
2. **Split.** Without `split` the body is one record. With it, every match of `record` starts a record that runs to the next match; text before the first match belongs to no record, and a record of only whitespace (an empty match after the last line break) is dropped. No record gives `Unmatched("no-records")`; more than 200 records give `ParseFailed(..., "too-many-records")`.
3. **Extract.** Per record. A value is read from at most 1,600 characters of the named group: NUL and control characters removed, whitespace collapsed, cut at 200 characters (so `record_result` accepts 16 details); an empty value is `None`. A time without a zone takes the zone of the mail's Date header, else UTC; one that cannot be read is `None`. Matches and values outside the record are read once per mail.
4. **Status.** The first rule that matches gives the status; none gives `unknown`. Unknown never becomes success.
5. **Spans** (test bench): `Span(field, start, end, source)` for every value read by a regex and for the status rule that matched (`status`). `source` is `body` (offsets in `Mail.body`) or the header; detail fields are named `details.<key>`.

### Bounds

- The text is `mime.message_text` (HTML through `html_text.py`), cut at 256 KiB characters (`MAX_TEXT`); the engine cuts a longer `Mail.body` too. Headers come decoded from at most 8,000 characters each.
- Every regex evaluation stops after 50 ms (`regex` timeout, spike 4 of C0-B) and runs with `concurrent=True`, so the GIL is released while it matches. One mail gets at most 5 seconds over all packs and records (`DEADLINE`), checked before every search and before every record of a split.
- The regex module measures its timeout as CPU time of the whole process (C `clock()`), so N parses at once give each pattern about 50 ms / N. C5-B runs parses on one worker thread, one mail at a time.
- A regex that runs out of memory (the module caps its backtracking stack at 1 GiB) gives `ParseFailed(..., "memory")`; `parse` and `apply` return an outcome for every mail and never raise for a pack the loader accepted.
- In the claim, a timeout or memory error skips only that pack (step 1). Once a pack has claimed the mail, a timeout fails the whole mail with the JSON Pointer of the pattern: it never lets a later status rule decide instead, so a failed rule that ran out of time cannot become success. The process continues with the next mail.

## Adding a vendor pack (C6-I)

Drop `app/parsers/packs/<id>.yaml` and `app/parsers/packs/fixtures/<id>/` in; `tests/parsers/test_fixtures.py` picks them up and checks that every listed fixture gives its expected results through `parse` with all built-in packs (so the claim is tested too), that every file in the folder is listed, that each fixture's results fit its class and that every span points at its value.

- Give at least two match conditions that hold for the vendor's mail (sender and subject, say): `generic-keywords` has one, so the vendor pack wins without a tie.
- Fixtures are synthetic unless a real mail was cleaned and permitted; names follow R-11 (example.com, example.net, .test, fictional companies) and no fixture holds a token-like or secret-looking literal (gitleaks runs in CI).
- `expected.json` is a list of objects with `status` and optionally `job_name`, `client_hint`, `run_id`, `started_at`, `finished_at` (ISO 8601 with a zone) and `details`; spans are not compared.
- Prefer possessive quantifiers (`[ \t]*+`) and bounded values (`\S[^\r\n]{0,199}`): a long line of a hostile mail then costs linear time and never reaches the timeout.

## generic-keywords

The fallback pack for any backup or job alert. It claims mail whose subject names a backup, job, task, copy, dump, sync and the like (one condition), takes the job name from the subject without a `[tag]`, `Re:` or the status words, the client, times, run id and details (`host`, `duration`, `processed`, `error`) from `Label: value` lines, and the status from the subject first (failed, warning, started, success), then a `Status:` line of the body, then keywords in the body. `0 errors`, `no errors`, `without errors`, `Errors: 0` and `Errors: none` at the end of a value are not failures; `Error: No such file` is one. `not successful`, `not yet completed`, `could not be completed`, `no successful backup`, `finished without success`, `didn't run` and other negated success words (up to two words such as yet, be or fully may sit after the negation) are failures and never count as success. Its fixtures are synthetic.

## Packs in the database (C5-B)

`parser_pack` (revision `c5_packs`): `id`, `version`, `vendor`, `status`, `source` (`builtin` or `custom`), `yaml`, `enabled`, `created_at`, `updated_at`. No client data, so it is not in the client delete map.

- **Built-in packs** are written from `app/parsers/packs` by `PackRepository.sync_builtin`, on every worker tick before parsing (a row that is already equal is not written). The files are read and parsed once per process (`shipped_pack_texts`, cached: they change only with a release), not on every tick. A new built-in pack is enabled; a changed one is updated in place and keeps the user's `enabled`; a built-in row the release no longer ships is removed. A custom pack whose id a later release ships stays custom.
- **Custom packs** are saved through the API. The text must load (`parse_pack`), its `id` must be the id in the URL, and a changed text must raise `version`.
- **ParserPackSource** (`app/ext/parsers.py`) gives the enabled packs as `PackText(id, source, yaml)` in id order; CE's `TablePackSource` reads the table. The worker and the test bench compile what it gives with `parse_pack_cached` (the same text is compiled once); a pack that no longer loads is left out and logged.

## The parse hook (C5-B, `app/worker/parse.py`)

A tick hook of the worker loop (`TICK_HOOKS`). Each tick it syncs the built-in packs, reads the enabled packs and builds the matcher once, then takes up to 200 pending messages, oldest first, one at a time with `FOR UPDATE SKIP LOCKED`, and parses each on the parser thread (one thread for the process, one mail at a time). It starts no new message once 30 seconds of the tick have passed (`PARSE_BUDGET`), so a slow custom pack that takes the 5 s deadline on every mail cannot hold the tick: the heartbeat stays inside the 3 minutes of `/readyz` and the later hooks run on time; the rest wait for the next tick. In the same transaction:

| Outcome | `parse_state` | Also |
| --- | --- | --- |
| `Parsed(pack_id, results)` | `parsed` | `record_result` per result with `received_at` of the message, bound to its job when the matcher is sure; `parse_pack_id`; `raw_message.client_id` when every result is bound to jobs of one client |
| `Unmatched(reason)` | `unmatched` | `parse_reason` `no-pack`, `tie` or `no-records`; no result |
| `ParseFailed(pack_id, path, reason)` | `error` | `parse_reason` `timeout`, `deadline`, `too-many-records` or `memory`; `parse_path`, `parse_pack_id` |
| anything else for one message | `error` | `parse_reason` `unreadable` (stored message over 5 MiB), `rejected` (a result the table refuses) or `internal`; logged by id, never with content |

`parsed_at` is the tick's time. A failing message never stops the tick. The message list and detail return the four columns. A pack the claim skipped for a message is logged as a warning with the message id, the reason and the path (never mail content); the message keeps the outcome the other packs gave it.

## The matcher (C5-B, `app/matcher/`)

Pure code. `tokens(text)`: NFKC, case folded, split at every run of characters that are not letters or digits. A result binds to a job when its `job_name` equals, token for token, the job's `match_key` or `name`, and its `client_hint` equals the client's name or one of its aliases; without a hint, no other job may have that name. Exactly one such job binds; none or several leave `job_id` NULL (the result waits in Unmatched). Archived jobs and jobs of archived clients are left out. `POST /results` with `client_hint` and `job_name` binds the same way at once.

## Packs and Unmatched API (C5-B)

Admins and technicians alike; lists, gets, export and suggest-schedule also take a read token; every change needs the CSRF token.

| Route | Does |
| --- | --- |
| `GET packs` | packs by id without YAML (`cursor`, `limit`) |
| `GET packs/{id}` | the pack with `yaml` |
| `PUT packs/{id}` `{yaml}` | create (201) or replace (200) a custom pack; 422 `issues` (`path`, `message`) when it does not load, the id differs or the version did not rise; 409 for a built-in id, and for a new id another request saved first (load and retry) |
| `POST packs/import` (file) | the same, id from the file |
| `GET packs/{id}/export` | the YAML as a file |
| `POST packs/{id}/enable`, `/disable` | from the worker's next tick |
| `POST packs/test` `{raw, pack?}` | `mail` (as the engine reads it), `scores` (packs not skipped), `claimed_by`, `outcome`, `pack_id`, `reason`, `path`, `candidates`, `results` with `spans`, `skipped`: `{pack_id, reason, path}` for a stored pack that no longer loads (`invalid`, path null) and for a pack whose claim failed (`timeout`, `deadline` or `memory`, at path) |
| `GET unmatched` | `result_id`, `raw_message_id`, `received_at`, `job_name`, `client_hint`, `status`, newest first |
| `POST unmatched/{result_id}/assign` `{job_id, replace_match_key?}` | binds; the job takes the result's job name as `match_key` when it had none, or, with `replace_match_key` true, when its key names another job name; the client takes the client hint as an alias when it does not know it and has room, so the next identical mail binds; other unmatched results with the same names bind too (`also_bound`), in one statement that skips a result another request bound meanwhile or holds right now (`FOR UPDATE SKIP LOCKED`), so concurrent assigns and create-jobs never wait for each other's results and cannot deadlock; messages are then refreshed in id order. Answers a binding (below) |
| `POST unmatched/{result_id}/create-job` | `client_id` or `client_name` (found or created), job fields (name and `match_key` default to the result's job name; without a schedule a daily one at the time suggest-schedule gives from one result on); then binds as assign |
| `GET unmatched/{result_id}/suggest-schedule?timezone=` | `kind` daily, `expr` HH:MM, `timezone` (default: the digest zone of Settings), `basis` (`finished`, `started` or `received`), `results`: the median local time of the newest 100 runs with the same names, around the clock, rounded down to 5 minutes; 422 below 3 runs |

**Test bench.** `packs/test` never runs in the worker and never on the web process's own threads: the regex timeout is CPU time of the whole process, and `ROLE=all` runs both in one process. The web process starts `python -m app.parsers.bench` per test (`app/api/bench.py`) with the request on stdin, PATH and the locale only (no setting or secret), at most 2 at once (a test that finds no free slot within 5 s answers 503 busy), killed after 20 s (503) or when its request is cancelled. The child has the engine's 50 ms and 5 s and its own limits (20 s CPU, 64 MiB address space). The route has its own limit (30 tests a minute per user) and body cap; the mail may have 1 MiB, the pack the loader's 64 KiB.

**Test bench memory** (C5-B2, F3). The web container has 384 MiB (`mem_limit: 384m` in `docker-compose.yml`; the same on Dokploy, where `ROLE=all` runs the web app and the worker in one process), and the bench children count against it. The child's address space is limited to 64 MiB (`MEMORY_BYTES`, `RLIMIT_AS`). A process's resident memory can never exceed its address space, so the two bench slots at their limit hold at most 2 x 64 = 128 MiB and the web process keeps the other 256 MiB.

Measured in CI (Python 3.12, C5-B2): the web process with the app, ingest and worker modules loaded holds 100 MiB resident; one Argon2 hash adds 66 MiB while it runs, and at most two run at once (docs/auth.md), so its peak is about 100 + 2 x 66 = 232 MiB. With both bench children at their limit that is 128 + 232 = 360 MiB, under 384 with 24 MiB for connections and request buffers. The child itself starts at 41 MiB of address space and peaked at 53 MiB (42 MiB resident) on the largest test the route lets through (1 MiB mail, an edited pack of 50 long rules and the built-in pack), so 64 MiB leaves it 11 MiB. `tests/api/test_packs_api.py` runs that test in the real child at its real limits. The child imports only the parser, the MIME reader, regex, PyYAML and jsonschema: `tests/parsers/test_bench.py` fails if it loads SQLAlchemy, FastAPI, pydantic, Argon2 or `app.db` (SQLAlchemy alone made it 79 MiB). The earlier 768 MiB was above the whole container, so two runaway children could have had the web process killed.

A child that runs out of memory answers `outcome` `error` with `reason` `memory`: at the pattern's `path` when a regex ran out (the engine maps the regex module's `MemoryError`), else with `path` null (the child maps any other `MemoryError` and answers once the request is freed). The web process only reads the answer, so it keeps serving; the test checks both with a child whose limit sits just above what its modules use.

**The binding** (C5-B2, for C5-F). assign and create-job (as `binding`) answer:

| Field | Meaning |
| --- | --- |
| `result_id`, `job_id`, `client_id` | what was bound |
| `match_key_set` | the job's `match_key` is now the result's job name: the job had none, or `replace_match_key` replaced another key. create-job: the new job has a key |
| `current_match_key` | the job's `match_key` after the call (null: none) |
| `replaced_match_key` | the key `replace_match_key` replaced; null otherwise |
| `client_alias_added` | the result's client hint is now an alias of the client |
| `reason` | why no alias was added: `no_client_hint` (the result has none), `already_known` (the client's name or an alias already), `alias_of_other_client` (another client, archived or not, has the hint as its name or an alias: adding it would make the hint name two clients), `alias_limit` (the client has its 50 aliases); null when one was added |
| `also_bound` | other unmatched results with the same names bound in the same call |

assign keeps a job's other key unless asked: with `replace_match_key` false (the default) a job whose `match_key` names another job name keeps it, and the answer has `match_key_set` false and that key in `current_match_key`. The next identical mail then waits in Unmatched again unless the job's name equals its job name, so C5-F shows the kept key and offers to assign again with `replace_match_key` true. A key of the same words (compared as the matcher compares them) is no other key and is not rewritten. A replacement writes the audit event `job.match_key_replaced` (target the job; details `result_id`, `old_match_key`, `new_match_key`) besides `unmatched.assign`. A job name without letters or digits is never made a key.

**Limits to know.** A message no pack claims has no result, so it is listed by `messages?parse_state=unmatched`, not by `unmatched`.
