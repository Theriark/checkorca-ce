"""The test bench child (python -m app.parsers.bench), called in this process.

The API tests run it as a real child process; here it is called directly so
its lines count for the coverage gate. Mail and packs are synthetic (R-11).
"""

import base64
import io
import json
import resource
from typing import Any

import pytest
import yaml

from app.parsers import bench
from app.parsers.loader import PACKS_DIR, PackInvalid

GENERIC = (PACKS_DIR / "generic-keywords.yaml").read_text("utf-8")
RAW = (
    b"From: Backup Server <backup@example.com>\r\n"
    b"To: alerts@example.net\r\n"
    b"Subject: [Failed] Nightly server backup\r\n"
    b"Date: Mon, 04 Jan 2027 03:05:00 +0000\r\n"
    b"\r\n"
    b"Client: Fictional Dental Clinic\r\n"
    b"Status: Failed\r\n"
    b"Finished: 2027-01-04 03:01:00\r\n"
)


def pack_text(pack_id: str = "example-tool", **changes: Any) -> str:
    document = {
        "id": pack_id,
        "version": 1,
        "vendor": "Example Tool",
        "status": "unverified-synthetic",
        "match": {"all": [{"from": r"@example\.com"}, {"subject": "Nightly"}]},
        "extract": {
            "job_name": {"regex": "(?P<name>Nightly [a-z ]+)", "in": "subject"}
        },
        "status_rules": [{"status": "failed", "regex": "(?i)status: failed"}],
    }
    document.update(changes)
    return yaml.safe_dump(document)


def test_the_claiming_pack_reads_the_mail_with_its_spans() -> None:
    answer = bench.run([("generic-keywords", GENERIC)], None, RAW)
    assert answer["claimed_by"] == "generic-keywords"
    assert answer["scores"] == [{"pack_id": "generic-keywords", "matched": 1}]
    assert (answer["outcome"], answer["pack_id"]) == ("parsed", "generic-keywords")
    assert answer["mail"]["subject"] == "[Failed] Nightly server backup"
    assert answer["mail"]["sent_at"] == "2027-01-04T03:05:00+00:00"
    (result,) = answer["results"]
    assert result["status"] == "failed"
    assert result["client_hint"] == "Fictional Dental Clinic"
    assert result["finished_at"] == "2027-01-04T03:01:00+00:00"
    sources = {"body": answer["mail"]["body"], "subject": answer["mail"]["subject"]}
    for span in result["spans"]:
        text = sources[span["source"]][span["start"] : span["end"]]
        if span["field"] == "job_name":
            assert text == "Nightly server backup"
        if span["field"] == "client_hint":
            assert text == "Fictional Dental Clinic"
    assert answer["skipped"] == []
    # The answer is plain JSON.
    assert json.loads(json.dumps(answer)) == answer


def test_the_edited_pack_replaces_the_stored_one_and_gives_the_results() -> None:
    stored = [
        ("example-tool", pack_text(vendor="Old")),
        ("generic-keywords", GENERIC),
        ("broken-tool", "id: ["),
    ]
    answer = bench.run(stored, pack_text(), RAW)
    # Two conditions beat the generic pack's one.
    assert answer["scores"] == [
        {"pack_id": "example-tool", "matched": 2},
        {"pack_id": "generic-keywords", "matched": 1},
    ]
    assert answer["claimed_by"] == "example-tool"
    (result,) = answer["results"]
    assert (result["job_name"], result["status"]) == ("Nightly server backup", "failed")
    invalid = {"pack_id": "broken-tool", "reason": "invalid", "path": None}
    assert answer["skipped"] == [invalid]


def test_a_slow_custom_pack_is_skipped_and_generic_keywords_claims() -> None:
    slow = pack_text("slow-tool", match={"all": [{"body": r"(?m)^(11+?)\1+$"}]})
    stored = [("slow-tool", slow), ("generic-keywords", GENERIC)]
    answer = bench.run(stored, None, RAW + b"1" * 199_999 + b"\r\n")
    assert answer["claimed_by"] == "generic-keywords"
    assert (answer["outcome"], answer["pack_id"]) == ("parsed", "generic-keywords")
    assert answer["scores"] == [{"pack_id": "generic-keywords", "matched": 1}]
    assert answer["skipped"] == [
        {"pack_id": "slow-tool", "reason": "timeout", "path": "/match/all/0/body"}
    ]


def test_an_edited_pack_that_claims_nothing_still_shows_its_results() -> None:
    elsewhere = pack_text(match={"all": [{"from": r"@example\.org"}]})
    answer = bench.run([], elsewhere, RAW)
    assert answer["scores"] == [{"pack_id": "example-tool", "matched": 0}]
    assert answer["claimed_by"] is None
    assert answer["outcome"] == "parsed"
    assert answer["results"][0]["status"] == "failed"


def test_unmatched_and_failed_outcomes() -> None:
    tie = bench.run([("one", pack_text("one")), ("two", pack_text("two"))], None, RAW)
    assert (tie["outcome"], tie["reason"]) == ("unmatched", "tie")
    assert tie["candidates"] == ["one", "two"] and tie["results"] == []
    none = bench.run([], None, RAW)
    assert (none["outcome"], none["reason"], none["claimed_by"]) == (
        "unmatched",
        "no-pack",
        None,
    )
    runaway = pack_text(
        status_rules=[{"status": "failed", "regex": r"(?m)^(11+?)\1+$"}]
    )
    ones = RAW + b"1" * 199_999 + b"\r\n"
    failed = bench.run([], runaway, ones)
    assert (failed["outcome"], failed["reason"]) == ("error", "timeout")
    assert failed["path"] == "/status_rules/0/regex"


def test_an_edited_pack_that_does_not_load_raises() -> None:
    with pytest.raises(PackInvalid):
        bench.run([], "id: [", RAW)


def test_main_limits_the_child_and_answers_on_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    limits: list[tuple[int, tuple[int, int]]] = []
    monkeypatch.setattr(
        resource, "setrlimit", lambda kind, values: limits.append((kind, values))
    )
    request = {
        "packs": [["generic-keywords", GENERIC]],
        "pack": None,
        "raw": base64.b64encode(RAW).decode(),
    }
    output = io.StringIO()
    assert bench.main(io.StringIO(json.dumps(request)), output) == 0
    assert json.loads(output.getvalue())["claimed_by"] == "generic-keywords"
    assert limits == [
        (resource.RLIMIT_CPU, (bench.CPU_SECONDS, bench.CPU_SECONDS)),
        (resource.RLIMIT_AS, (bench.MEMORY_BYTES, bench.MEMORY_BYTES)),
    ]
