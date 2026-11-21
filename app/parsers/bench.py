"""The test bench of POST packs/test, run as a child of the web process.

  python -m app.parsers.bench < request.json > answer.json

The web process starts one child per test (app/api/bench.py) and never runs a
pasted mail or a user's pack itself: the regex module measures its 50 ms
timeout in CPU time of the whole process, and ROLE=all runs the web app and
the worker in one process. The child has its own CPU clock, the same 50 ms
and 5 s limits as the worker, and limits of its own (CPU_SECONDS, MEMORY_BYTES)
in case anything else runs away.

Request (JSON): packs, a list of [id, Pack YAML] (the enabled packs); pack,
the Pack YAML being edited or null; raw, the mail as base64. The edited pack
takes the place of a stored pack with its id. Answer (JSON): the mail as the
engine reads it, every pack's score, the claiming pack, the outcome with its
results and spans, and the packs left out (skipped): stored packs that do
not load (reason invalid) and packs whose claim failed (timeout, deadline or
memory, at path).
"""

import base64
import json
import sys
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Final, TextIO

from app.ingest.results import ParsedResult
from app.parsers.engine import Mail, Outcome, Parsed, ParseFailed, bench, mail_from_raw
from app.parsers.loader import PackInvalid, parse_pack_cached
from app.parsers.model import Pack

# Limits of the child process: CPU seconds and address space.
CPU_SECONDS: Final = 20
MEMORY_BYTES: Final = 768 * 1024 * 1024


def _time(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _result(result: ParsedResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "job_name": result.job_name,
        "client_hint": result.client_hint,
        "started_at": _time(result.started_at),
        "finished_at": _time(result.finished_at),
        "run_id": result.run_id,
        "details": dict(result.details),
        "spans": [
            {
                "field": span.field,
                "start": span.start,
                "end": span.end,
                "source": span.source,
            }
            for span in result.spans
        ],
    }


def _outcome(outcome: Outcome) -> dict[str, Any]:
    if isinstance(outcome, Parsed):
        return {
            "outcome": "parsed",
            "pack_id": outcome.pack_id,
            "reason": None,
            "path": None,
            "candidates": [],
            "results": [_result(result) for result in outcome.results],
        }
    if isinstance(outcome, ParseFailed):
        return {
            "outcome": "error",
            "pack_id": outcome.pack_id,
            "reason": outcome.reason,
            "path": outcome.path,
            "candidates": [],
            "results": [],
        }
    return {
        "outcome": "unmatched",
        "pack_id": None,
        "reason": outcome.reason,
        "path": None,
        "candidates": list(outcome.candidates),
        "results": [],
    }


def _mail(mail: Mail) -> dict[str, Any]:
    return {
        "sender": mail.sender,
        "to": mail.to,
        "subject": mail.subject,
        "body": mail.body,
        "sent_at": _time(mail.sent_at),
    }


def _skipped(pack_id: str, reason: str, path: str | None) -> dict[str, Any]:
    return {"pack_id": pack_id, "reason": reason, "path": path}


def run(
    stored: Sequence[tuple[str, str]], edited: str | None, raw: bytes
) -> dict[str, Any]:
    """The bench answer for one mail. Raises PackInvalid for an edited pack
    that does not load (the web process checks it first)."""
    pack = None if edited is None else parse_pack_cached(edited)
    packs: list[Pack] = [] if pack is None else [pack]
    skipped: list[dict[str, Any]] = []
    for pack_id, text in stored:
        if pack is not None and pack_id == pack.id:
            continue
        try:
            packs.append(parse_pack_cached(text))
        except PackInvalid:
            skipped.append(_skipped(pack_id, "invalid", None))
    packs.sort(key=lambda item: item.id)
    mail = mail_from_raw(raw)
    shown = bench(packs, mail, pack=pack)
    skipped += [
        _skipped(item.pack_id, item.reason, item.path)
        for item in shown.outcome.skipped
    ]
    return {
        "mail": _mail(mail),
        "scores": [
            {"pack_id": score.pack_id, "matched": score.matched}
            for score in shown.scores
        ],
        "claimed_by": shown.claimed_by,
        **_outcome(shown.outcome),
        "skipped": skipped,
    }


def answer(request: dict[str, Any]) -> dict[str, Any]:
    """run() on a request as the web process writes it."""
    stored = [(str(pack_id), str(text)) for pack_id, text in request["packs"]]
    edited = request["pack"]
    raw = base64.b64decode(request["raw"], validate=True)
    return run(stored, None if edited is None else str(edited), raw)


def limit_resources() -> None:
    """CPU time and memory of this process (Linux and other Unix systems)."""
    import resource

    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))


def main(stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> int:
    limit_resources()
    request = json.load(stdin)
    json.dump(answer(request), stdout, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
