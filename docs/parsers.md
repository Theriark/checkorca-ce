# Parser packs and the parser engine

Phase C5-I (Integration and Protocol Engineer) built the pack format, the loader, the engine and the `generic-keywords` pack. C5-B adds the `parser_pack` table, the matcher and the worker's parse hook; C5-F the Unmatched and parser screens; C6-I the vendor packs. Source: dev-work-plan rev 35, section C5 and the Interfaces chapter (Pack YAML, ParsedResult).

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

## Loading (`app/parsers/loader.py`)

```python
from app.parsers.loader import PackInvalid, builtin_packs, parse_pack

try:
    pack = parse_pack(yaml_text)
except PackInvalid as invalid:
    issues = [{"path": i.path, "message": i.message} for i in invalid.issues]
```

- At most 64 KiB of text. PyYAML's safe loader only; aliases (`*name`) are refused (a few lines of anchors and aliases expand exponentially once walked), and so are duplicate keys and nesting deeper than 10 levels, checked on the event stream before anything recursive runs. Python tags, several documents and integers of more than 4,300 digits are refused as invalid YAML.
- Then the schema, then the checks a schema cannot express: every regex compiles, an extract regex has exactly one named group, a field gives `regex` or `literal` (and `in`/`format` only with `regex`), fixture names are unique, verified has 3 fixture classes.
- `PackIssue.path` is a JSON Pointer into the pack (`/status_rules/2/regex`; `""` is the whole document), `message` at most 300 characters. All issues of one pass come together, ordered by path. C5-B answers them with 422; C5-F shows each beside its line.
- `builtin_packs()` loads `app/parsers/packs/*.yaml` in file name order and refuses a file whose id is not its name. `pack_fixtures(pack)` yields the listed fixtures with their expected `ParsedResult`s.

## The engine (`app/parsers/engine.py`)

```python
from app.parsers.engine import ParseFailed, Parsed, Unmatched, mail_from_raw, parse

outcome = await asyncio.to_thread(parse, packs, mail_from_raw(raw))
match outcome:
    case Parsed(pack_id, results): ...      # record_result(..., raw_message_id=message.id) for each; parse_state parsed
    case Unmatched(reason, candidates): ... # parse_state unmatched; reason no-pack, tie or no-records
    case ParseFailed(pack_id, path, reason): ...  # parse_state error; reason timeout, deadline or too-many-records
```

1. **Claim.** A pack claims the mail when every `match.all` condition and at least one `match.any` condition match. Its score is the number of matching conditions. The highest score wins; a tie between the best packs gives `Unmatched("tie", ids)`, no claim gives `Unmatched("no-pack")`. `apply(pack, mail)` skips the claim (a job's own pack, the test bench).
2. **Split.** Without `split` the body is one record. With it, every match of `record` starts a record that runs to the next match; text before the first match belongs to no record. No match gives `Unmatched("no-records")`; more than 200 records give `ParseFailed(..., "too-many-records")`.
3. **Extract.** Per record. A value is the named group's text with NUL and control characters removed, whitespace collapsed and cut at 200 characters (so `record_result` accepts 16 details); an empty value is `None`. A time without a zone takes the zone of the mail's Date header, else UTC; one that cannot be read is `None`. Matches outside the record are computed once per mail.
4. **Status.** The first rule that matches gives the status; none gives `unknown`. Unknown never becomes success.
5. **Spans** (test bench): `Span(field, start, end, source)` for every value read by a regex and for the status rule that matched (`status`). `source` is `body` (offsets in `Mail.body`) or the header; detail fields are named `details.<key>`.

### Bounds

- The text is `mime.message_text` (HTML through `html_text.py`), cut at 256 KiB characters (`MAX_TEXT`); the engine cuts a longer `Mail.body` too. Headers come decoded from at most 8,000 characters each.
- Every regex evaluation stops after 50 ms (`regex` timeout, spike 4 of C0-B) and runs with `concurrent=True`, so the GIL is released while it matches. One mail gets at most 5 seconds of evaluations over all packs and records (`DEADLINE`).
- A timeout fails the whole mail with the JSON Pointer of the pattern: it never lets a later status rule or a weaker pack decide instead, so a failed rule that ran out of time cannot become success. The process continues with the next mail.

## Adding a vendor pack (C6-I)

Drop `app/parsers/packs/<id>.yaml` and `app/parsers/packs/fixtures/<id>/` in; `tests/parsers/test_fixtures.py` picks them up and checks that every listed fixture gives its expected results through `parse` with all built-in packs (so the claim is tested too), that every file in the folder is listed, that each fixture's results fit its class and that every span points at its value.

- Give at least two match conditions that hold for the vendor's mail (sender and subject, say): `generic-keywords` has one, so the vendor pack wins without a tie.
- Fixtures are synthetic unless a real mail was cleaned and permitted; names follow R-11 (example.com, example.net, .test, fictional companies) and no fixture holds a token-like or secret-looking literal (gitleaks runs in CI).
- `expected.json` is a list of objects with `status` and optionally `job_name`, `client_hint`, `run_id`, `started_at`, `finished_at` (ISO 8601 with a zone) and `details`; spans are not compared.
- Prefer possessive quantifiers (`[ \t]*+`) and bounded values (`\S[^\r\n]{0,199}`): a long line of a hostile mail then costs linear time and never reaches the timeout.

## generic-keywords

The fallback pack for any backup or job alert. It claims mail whose subject names a backup, job, task, copy, dump, sync and the like (one condition), takes the job name from the subject without a `[tag]`, `Re:` or the status words, the client, times, run id and details (`host`, `duration`, `processed`, `error`) from `Label: value` lines, and the status from the subject first (failed, warning, started, success), then a `Status:` line of the body, then keywords in the body. `0 errors`, `no errors`, `without errors` and `Errors: 0` are not failures. Its fixtures are synthetic.
