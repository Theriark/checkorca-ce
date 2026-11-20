"""The parser engine: claim, split, extract, status rules and the bounds on
regex time. Mail and names are synthetic (R-11)."""

import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from itertools import chain, repeat
from math import isqrt
from typing import Any

import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

from app.ingest.results import Span
from app.parsers.engine import (
    MAX_RECORDS,
    MAX_TEXT,
    MAX_VALUE,
    Mail,
    Parsed,
    ParseFailed,
    Unmatched,
    apply,
    mail_from_raw,
    parse,
)
from app.parsers.loader import builtin_packs, parse_pack
from app.parsers.model import Pack

GENERIC = next(pack for pack in builtin_packs() if pack.id == "generic-keywords")
# Backtrack without end on a run of 1s of prime length (spike 4 of C0-B).
RUNAWAY = r"^(11+?)\1+$"
NAMED_RUNAWAY = r"^(?P<v>11+?)(?P=v)+$"


def prime_below(limit: int) -> int:
    def is_prime(number: int) -> bool:
        return all(number % divisor for divisor in range(2, isqrt(number) + 1))

    return next(number for number in range(limit, 2, -1) if is_prime(number))


ONES = "1" * prime_below(200_000)


def make_pack(pack_id: str = "example-tool", **changes: Any) -> Pack:
    document: dict[str, Any] = {
        "id": pack_id,
        "version": 1,
        "vendor": "Example Tool",
        "status": "unverified-synthetic",
        "match": {"all": [{"from": r"@example\.com"}]},
        "status_rules": [
            {"status": "failed", "regex": "(?i)failed"},
            {"status": "success", "regex": "(?i)success"},
        ],
    }
    document.update(changes)
    return parse_pack(yaml.safe_dump(document))


def mail(body: str = "", **headers: Any) -> Mail:
    values: dict[str, Any] = {"sender": "alerts@example.com", "subject": "Report"}
    values.update(headers)
    return Mail(body=body, **values)


def parsed(outcome: object) -> Parsed:
    assert isinstance(outcome, Parsed), outcome
    return outcome


def only(outcome: object) -> Any:
    (result,) = parsed(outcome).results
    return result


# Claim


def test_the_pack_with_most_matching_conditions_claims_the_mail() -> None:
    one = make_pack("one")
    two = make_pack(
        "two", match={"all": [{"from": "example"}, {"subject": "(?i)report"}]}
    )
    outcome = parse([one, two], mail("Status: success"))
    assert parsed(outcome).pack_id == "two"


def test_every_matching_any_condition_counts() -> None:
    one = make_pack("one", match={"all": [{"from": "example"}, {"to": "net"}]})
    any_two = make_pack(
        "any-two",
        match={"any": [{"subject": "Report"}, {"body": "Job"}, {"body": "absent"}]},
    )
    alerts = mail("Job done", to="inbox@example.net")
    assert parse([one, any_two], alerts) == Unmatched("tie", ("one", "any-two"))
    alerts = mail("Job success", subject="Report", to="inbox@example.org")
    assert parsed(parse([one, any_two], alerts)).pack_id == "any-two"


def test_a_tie_between_the_best_packs_is_unmatched() -> None:
    packs = [make_pack("one"), make_pack("two")]
    assert parse(packs, mail("success")) == Unmatched("tie", ("one", "two"))


def test_mail_no_pack_claims_is_unmatched() -> None:
    no_pack = Unmatched("no-pack")
    assert parse([make_pack()], mail(sender="alerts@example.org")) == no_pack
    assert parse([], mail()) == no_pack


def test_all_conditions_and_one_any_condition_must_match() -> None:
    no_pack = Unmatched("no-pack")
    pack = make_pack(match={"all": [{"from": "example"}], "any": [{"subject": "x"}]})
    assert parse([pack], mail(sender="alerts@other.test", subject="x")) == no_pack
    assert parse([pack], mail(subject="nothing")) == no_pack
    assert parsed(parse([pack], mail(subject="x"))).pack_id == "example-tool"


# Split


DIGEST = """Daily digest for Fictional Dental Clinic
Job: Server backup
Result: Success
Job: Mail archive
Result: Warning, 2 items skipped
Job: Database dump
Result: Failed
"""


def digest_pack(**changes: Any) -> Pack:
    document: dict[str, Any] = {
        "split": {"record": "(?m)^Job: "},
        "extract": {
            "job_name": {"regex": "^Job: (?P<name>[^\\n]+)"},
            "client_hint": {"regex": "for (?P<client>[^\\n]+)", "in": "body"},
            "run_id": {"literal": "digest-1"},
        },
        "status_rules": [
            {"status": "failed", "regex": "Result: Failed"},
            {"status": "warning", "regex": "Result: Warning"},
            {"status": "success", "regex": "Result: Success"},
        ],
    }
    document.update(changes)
    return make_pack(**document)


def test_a_digest_of_3_records_gives_3_results() -> None:
    outcome = parsed(parse([digest_pack()], mail(DIGEST)))
    got = [(result.job_name, result.status) for result in outcome.results]
    assert got == [
        ("Server backup", "success"),
        ("Mail archive", "warning"),
        ("Database dump", "failed"),
    ]
    hints = {result.client_hint for result in outcome.results}
    assert hints == {"Fictional Dental Clinic"}
    assert {result.run_id for result in outcome.results} == {"digest-1"}
    for result in outcome.results:
        for span in result.spans:
            assert span.source == "body"
            value = DIGEST[span.start : span.end]
            if span.field == "job_name":
                assert value == result.job_name
            if span.field == "status":
                assert value.startswith("Result: ")


def test_a_split_without_a_record_is_unmatched() -> None:
    outcome = parse([digest_pack()], mail("No jobs today."))
    assert outcome == Unmatched("no-records", ("example-tool",))


def test_a_split_gives_at_most_max_records() -> None:
    body = "Job: x\nResult: Success\n" * MAX_RECORDS
    assert len(parsed(parse([digest_pack()], mail(body))).results) == MAX_RECORDS
    outcome = parse([digest_pack()], mail(body + "Job: y\n"))
    assert outcome == ParseFailed("example-tool", "/split/record", "too-many-records")


def test_an_empty_split_match_moves_on() -> None:
    pack = digest_pack(split={"record": "(?m)^"})
    outcome = parsed(parse([pack], mail("Job: a\nJob: b\nJob: c")))
    assert [result.job_name for result in outcome.results] == ["a", "b", "c"]


def test_a_record_of_only_whitespace_is_no_record() -> None:
    # (?m)^ also matches after the last line break: no phantom unknown result.
    pack = digest_pack(split={"record": "(?m)^"})
    outcome = parsed(parse([pack], mail("Job: a\nJob: b\n \n")))
    assert [result.job_name for result in outcome.results] == ["a", "b"]
    assert parse([pack], mail(" \n\n")) == Unmatched("no-records", ("example-tool",))


def test_the_deadline_is_checked_before_every_record() -> None:
    # Start, 4 split searches, record 1 (check, status search): then time is up.
    clock = chain(repeat(0.0, 7), repeat(100.0)).__next__
    rules = [{"status": "success", "regex": "Report", "in": "subject"}]
    pack = digest_pack(status_rules=rules, extract={})
    body = "Job: a\nJob: b\nJob: c\n"
    outcome = apply(pack, mail(body), clock=clock)
    assert outcome == ParseFailed("example-tool", "/split/record", "deadline")


def test_values_outside_the_record_are_read_once_per_mail() -> None:
    extract = {"job_name": {"regex": "(?s)(?P<all>.+)", "in": "body"}}
    for index in range(16):
        extract.setdefault("details", {})[f"d{index}"] = {
            "regex": "(?s)(?P<all>.+)",
            "in": "body",
        }
    pack = make_pack(split={"record": "(?m)^R$"}, extract=extract)
    body = "R\n" * MAX_RECORDS + "x " * 120_000
    started = time.perf_counter()
    outcome = parsed(apply(pack, mail(body)))
    assert time.perf_counter() - started < 2.0
    assert len(outcome.results) == MAX_RECORDS
    assert outcome.results[0].job_name == outcome.results[-1].job_name


# Status


def test_the_first_matching_status_rule_wins() -> None:
    assert only(parse([make_pack()], mail("success, then failed"))).status == "failed"


def test_no_matching_rule_gives_unknown() -> None:
    result = only(parse([make_pack()], mail("The task ran.")))
    assert result.status == "unknown"
    assert result.spans == ()


def test_a_status_rule_can_read_the_subject() -> None:
    rules = [{"status": "warning", "regex": "(?i)warn", "in": "subject"}]
    pack = make_pack(status_rules=rules)
    result = only(parse([pack], mail("Status: ok", subject="Copy: WARNING")))
    assert result.status == "warning"
    assert result.spans == (Span("status", 6, 10, "subject"),)


# Extract


def test_fields_read_their_scope_and_record_their_span() -> None:
    pack = make_pack(
        extract={
            "job_name": {"regex": "^(?P<job>[^:]+)", "in": "subject"},
            "client_hint": {"regex": "@(?P<domain>.+)$", "in": "from"},
            "run_id": {"regex": "^(?P<box>[^@]+)", "in": "to"},
            "details": {"size": {"regex": "Size: (?P<size>.+)"}},
        }
    )
    alerts = mail(
        "Status: success\nSize: 1 GB",
        subject="Nightly server backup: success",
        to="box-7@example.net",
    )
    result = only(parse([pack], alerts))
    assert result.job_name == "Nightly server backup"
    assert result.client_hint == "example.com"
    assert result.run_id == "box-7"
    assert result.details == {"size": "1 GB"}
    assert Span("details.size", 22, 26, "body") in result.spans
    assert Span("job_name", 0, 21, "subject") in result.spans
    assert Span("client_hint", 7, 18, "from") in result.spans
    assert Span("run_id", 0, 5, "to") in result.spans


def test_a_literal_has_no_span() -> None:
    pack = make_pack(
        extract={"job_name": {"literal": "Nightly"}, "details": {"k": {"literal": "v"}}}
    )
    result = only(parse([pack], mail("success")))
    assert (result.job_name, result.details) == ("Nightly", {"k": "v"})
    assert [span.field for span in result.spans] == ["status"]


def test_values_are_cleaned_and_cut() -> None:
    pack = make_pack(
        extract={
            "job_name": {"regex": "Job:(?P<job>[^\\n]*)"},
            "client_hint": {"regex": "Client:(?P<client>[^\\n]*)"},
            "run_id": {"regex": "Run:(?P<run>[^\\n]*)"},
            "details": {
                "optional": {"regex": "(?:(?P<x>never)|Job)"},
                "blank": {"regex": "Blank:(?P<blank>[ ]*)"},
            },
        }
    )
    body = (
        "Job:  Nightly \x01\x7f server\x00  backup \n"
        f"Client: {'a' * 300}\nRun:\nBlank:   \n"
    )
    result = only(parse([pack], mail(body)))
    assert result.job_name == "Nightly server backup"
    assert result.client_hint == "a" * MAX_VALUE
    assert result.run_id is None
    assert result.details == {}


# Times


def times_pack(**started: str) -> Pack:
    return make_pack(
        extract={
            "started_at": {"regex": "Started: (?P<at>[^\\n]+)", **started},
            "finished_at": {"regex": "Finished: (?P<at>[^\\n]+)"},
        }
    )


PLUS_ONE = timezone(timedelta(hours=1))


def test_a_time_with_a_zone_keeps_it() -> None:
    body = "Started: 2026-11-20T03:00:00+01:00\nFinished: 2026-11-20T02:05:00Z"
    result = only(parse([times_pack()], mail(body)))
    assert result.started_at == datetime(2026, 11, 20, 3, tzinfo=PLUS_ONE)
    assert result.finished_at == datetime(2026, 11, 20, 2, 5, tzinfo=UTC)


def test_a_time_without_a_zone_takes_the_zone_of_the_date_header() -> None:
    sent = datetime(2026, 11, 20, 3, 6, tzinfo=PLUS_ONE)
    alerts = mail("Started: 2026-11-20 03:00:00", sent_at=sent)
    result = only(parse([times_pack()], alerts))
    assert result.started_at == datetime(2026, 11, 20, 3, tzinfo=PLUS_ONE)
    assert result.started_at.utcoffset() == timedelta(hours=1)


def test_a_time_without_a_zone_or_date_header_is_utc() -> None:
    result = only(parse([times_pack()], mail("Started: 2026-11-20 03:00:00")))
    assert result.started_at == datetime(2026, 11, 20, 3, tzinfo=UTC)


def test_rfc_2822_and_strptime_times_are_read() -> None:
    body = "Started: 20/11/2026 03:00\nFinished: Fri, 20 Nov 2026 03:05:00 +0100"
    result = only(parse([times_pack(format="%d/%m/%Y %H:%M")], mail(body)))
    assert result.started_at == datetime(2026, 11, 20, 3, tzinfo=UTC)
    assert result.finished_at == datetime(2026, 11, 20, 3, 5, tzinfo=PLUS_ONE)


def test_a_time_that_cannot_be_read_is_empty() -> None:
    body = "Started: 2026-31-31 03:00\nFinished: yesterday evening"
    result = only(parse([times_pack(format="%Y-%m-%d %H:%M")], mail(body)))
    assert (result.started_at, result.finished_at) == (None, None)


# The bounds on regex time


def test_a_redos_pattern_times_out_and_the_engine_continues() -> None:
    rules = [
        {"status": "failed", "regex": RUNAWAY},
        {"status": "success", "regex": "1"},
    ]
    pack = make_pack(status_rules=rules)
    started = time.perf_counter()
    outcome = parse([pack], mail(ONES))
    assert time.perf_counter() - started < 1.0
    # Never the success rule behind the one that timed out.
    assert outcome == ParseFailed("example-tool", "/status_rules/0/regex", "timeout")
    assert only(parse([pack], mail("11 is prime"))).status == "success"
    later = parse([GENERIC], mail(subject="Nightly backup failed"))
    assert only(later).status == "failed"


def test_a_timeout_names_the_pattern_it_came_from() -> None:
    cases = [
        (make_pack(match={"all": [{"body": RUNAWAY}]}), "/match/all/0/body"),
        (make_pack(match={"any": [{"body": RUNAWAY}]}), "/match/any/0/body"),
        (
            make_pack(extract={"job_name": {"regex": NAMED_RUNAWAY}}),
            "/extract/job_name/regex",
        ),
        (
            make_pack(extract={"details": {"k": {"regex": NAMED_RUNAWAY}}}),
            "/extract/details/k/regex",
        ),
        (make_pack(split={"record": RUNAWAY}), "/split/record"),
    ]
    for pack, path in cases:
        outcome = parse([pack], mail(ONES))
        assert outcome == ParseFailed("example-tool", path, "timeout")


def test_a_spent_deadline_fails_the_mail() -> None:
    claim = ParseFailed("example-tool", "/match/all/0/from", "deadline")
    assert parse([make_pack()], mail(), deadline=0) == claim
    status = ParseFailed("example-tool", "/status_rules/0/regex", "deadline")
    assert apply(make_pack(), mail(), deadline=-1) == status


def test_a_timeout_after_most_of_the_deadline_is_the_deadline() -> None:
    clock = chain([0.0], repeat(0.99)).__next__
    pack = make_pack(match={"all": [{"body": RUNAWAY}]})
    outcome = parse([pack], mail(ONES), deadline=1.0, clock=clock)
    assert outcome == ParseFailed("example-tool", "/match/all/0/body", "deadline")


def test_the_text_is_cut_at_max_text() -> None:
    rules = [{"status": "failed", "regex": "MARK"}]
    pack = make_pack(status_rules=rules)
    long_mail = mail("x" * MAX_TEXT + "MARK")
    assert only(parse([pack], long_mail)).status == "unknown"
    assert only(apply(pack, long_mail)).status == "unknown"
    assert only(apply(pack, mail("x" * (MAX_TEXT - 4) + "MARK"))).status == "failed"


class OutOfMemory:
    def search(self, *args: object, **kwargs: object) -> None:
        raise MemoryError


def test_a_regex_out_of_memory_fails_the_mail() -> None:
    pack = make_pack()
    (condition,) = pack.match_all
    broken = replace(pack, match_all=(replace(condition, pattern=OutOfMemory()),))
    outcome = parse([broken], mail())
    assert outcome == ParseFailed("example-tool", "/match/all/0/from", "memory")


def test_a_time_format_strptime_cannot_compile_reads_nothing() -> None:
    # The loader refuses "%d %d"; a Pack built another way still never raises.
    pack = times_pack()
    started, finished = pack.fields
    broken = replace(pack, fields=(replace(started, time_format="%d %d"), finished))
    result = only(parse([broken], mail("Started: 20 20")))
    assert result.started_at is None


def test_apply_reads_mail_the_pack_would_not_claim() -> None:
    outcome = apply(make_pack(), mail("success", sender="other@example.org"))
    assert only(outcome).status == "success"


# Reading a raw message


RAW = b"""From: =?utf-8?q?Backup_Server?= <backup@example.com>
To: alerts@example.net
Subject: =?utf-8?q?Nightly_backup_=E2=9C=93?=
Date: Fri, 20 Nov 2026 03:05:30 +0100
Message-ID: <engine-raw@example.com>
MIME-Version: 1.0
Content-Type: text/html; charset=utf-8

<p>Status: success</p><script>Status: failed</script>
"""


def test_a_raw_message_gives_its_headers_and_visible_text() -> None:
    alerts = mail_from_raw(RAW)
    assert alerts.sender == "Backup Server <backup@example.com>"
    assert alerts.to == "alerts@example.net"
    assert alerts.subject == "Nightly backup ✓"
    assert alerts.body == "Status: success"
    assert alerts.sent_at == datetime(2026, 11, 20, 3, 5, 30, tzinfo=PLUS_ONE)


def test_a_date_header_is_read_with_care() -> None:
    def sent_at(date: bytes) -> datetime | None:
        return mail_from_raw(b"Subject: x\n" + date + b"\n\nbody\n").sent_at

    unknown_zone = sent_at(b"Date: Fri, 20 Nov 2026 03:05:30 -0000")
    assert unknown_zone == datetime(2026, 11, 20, 3, 5, 30, tzinfo=UTC)
    assert sent_at(b"Date: not a date") is None
    assert sent_at(b"Date:   ") is None
    assert sent_at(b"X-Other: 1") is None
    assert mail_from_raw(b"").subject == ""


# Unknown never becomes success


NEGATED_SUCCESS = [
    "was not successful",
    "could not complete",
    "has not finished",
    "not completed",
    "has not been completed",
    "did not run",
    "didn't run",
    "couldn't complete",
    "was unable to complete",
    "never finished",
]


def test_a_negated_success_word_is_a_failure_in_the_generic_pack() -> None:
    for phrase in NEGATED_SUCCESS:
        subject = only(parse([GENERIC], mail(subject=f"Nightly backup {phrase}")))
        assert (phrase, subject.status) == (phrase, "failed")
        assert subject.job_name == "Nightly backup"
        body = only(parse([GENERIC], mail(f"The backup {phrase}.", subject="Backup")))
        assert (phrase, body.status) == (phrase, "failed")


def test_the_generic_pack_reads_a_large_benign_mail_in_time() -> None:
    # The slowest generic rules scan the whole body; with the real module they
    # must stay well inside the 50 ms timeout on a full 256 KiB text.
    line = "2026-11-20 01:00:07 INFO copied file 1234 of 9999 to share FS-01\n"
    body = (line * (MAX_TEXT // len(line) + 1))[:MAX_TEXT]
    outcome = parse([GENERIC], mail(body, subject="Nightly backup report"))
    assert only(outcome).status == "unknown"


def test_success_words_still_count_in_the_generic_pack() -> None:
    for subject in ("Nightly backup completed", "Nightly backup: OK"):
        assert only(parse([GENERIC], mail(subject=subject))).status == "success"
    plain = mail("It completed successfully with 0 errors.", subject="Backup")
    assert only(parse([GENERIC], plain)).status == "success"


def first_rule_status(pack: Pack, alerts: Mail) -> str:
    """The status of the first rule that matches: the engine's definition."""
    for rule in pack.status_rules:
        text = alerts.subject if rule.where == "subject" else alerts.body
        if rule.pattern.search(text):
            return rule.status
    return "unknown"


# Status words, their negations and noise, so the rules are reached.
WORDS = st.sampled_from(
    [
        "success",
        "successful",
        "completed",
        "OK",
        "failed",
        "not",
        "could not",
        "no",
        "0",
        "errors",
        "Errors: 0",
        "warning",
        "started",
        "Status:",
        "\n",
    ]
)
STATUS_TEXT = st.lists(WORDS | st.text(max_size=8), max_size=30).map(" ".join)


@settings(max_examples=300, deadline=None)
@given(STATUS_TEXT | st.text(max_size=400), STATUS_TEXT | st.text(max_size=120))
def test_unknown_never_becomes_success(body: str, subject: str) -> None:
    alerts = mail(body, subject="Nightly backup " + subject)
    result = only(parse([GENERIC], alerts))
    expected = first_rule_status(GENERIC, alerts)
    assert result.status == expected
    status_spans = [span for span in result.spans if span.field == "status"]
    assert bool(status_spans) == (expected != "unknown")


# The long s folds to s under (?i).
NO_S = st.characters(exclude_characters="Ssſ")


@settings(max_examples=300, deadline=None)
@given(st.text(alphabet=NO_S, max_size=400))
def test_without_a_success_rule_match_there_is_no_success(body: str) -> None:
    assert only(parse([make_pack()], mail(body))).status in ("failed", "unknown")
