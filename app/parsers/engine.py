"""The parser engine: which pack claims a mail, and the results it reads.

Pure and synchronous. C5-B calls parse() from the worker's parse hook in a
thread, one mail at a time (asyncio.to_thread; the regex module releases the
GIL while it matches), and the test bench of C5-F calls apply() on a pasted
sample.

1. Claim: a pack claims a mail when every condition of its match.all and at
   least one of its match.any match. The pack with the most matching
   conditions wins; a tie between the best packs is Unmatched (tie).
2. Split: without split the body is one record; with split every match of the
   record regex starts a record that runs to the next match.
3. Extract: per record, the text of each field regex's only named group, or
   the literal. A regex that finds nothing leaves the field empty.
4. Status: the status rules in order; the first that matches gives the
   status, none matching gives unknown. Unknown never counts as success.

Mail is hostile and packs are user input, so the cost is bounded:

- the text is the visible text of the mail (app.ingest.mime.message_text,
  HTML through app/ingest/html_text.py), cut at MAX_TEXT characters;
- every regex evaluation stops after REGEX_TIMEOUT (the regex module's
  timeout, spike 4 of C0-B);
- all evaluations for one mail share DEADLINE seconds, checked again before
  every record of a split, and a split may give at most MAX_RECORDS records;
- a value is read from at most 1,600 characters of its match.

The regex module measures its timeout in CPU time of the whole process, so
C5-B parses on one thread. A timeout fails the whole mail (ParseFailed names
the pattern). It never lets a later status rule or a weaker pack decide
instead: a failed rule that timed out must not turn into success.
"""

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Final, Literal

import regex

from app.ingest import mime
from app.ingest.results import ParsedResult, ResultStatus, Span
from app.parsers.model import (
    MAX_VALUE,
    TIME_FIELDS,
    Condition,
    Extractor,
    Pack,
    Scope,
    clean_value,
)

REGEX_TIMEOUT: Final = 0.05
DEADLINE: Final = 5.0
MAX_TEXT: Final = mime.MAX_TEXT
MAX_RECORDS: Final = 200

UnmatchedReason = Literal["no-pack", "tie", "no-records"]
FailReason = Literal["timeout", "deadline", "too-many-records", "memory"]

__all__ = [
    "DEADLINE",
    "MAX_RECORDS",
    "MAX_TEXT",
    "MAX_VALUE",
    "REGEX_TIMEOUT",
    "Mail",
    "Outcome",
    "ParseFailed",
    "Parsed",
    "Unmatched",
    "apply",
    "mail_from_raw",
    "parse",
]


@dataclass(frozen=True, slots=True)
class Mail:
    """What the engine reads of a message: three headers, decoded, the
    visible text of the body and the Date header."""

    sender: str = ""
    to: str = ""
    subject: str = ""
    body: str = ""
    sent_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class Parsed:
    pack_id: str
    results: tuple[ParsedResult, ...]


@dataclass(frozen=True, slots=True)
class Unmatched:
    """No pack claimed the mail (no-pack), the best packs tied (candidates
    names them) or the pack's split found no record (no-records)."""

    reason: UnmatchedReason
    candidates: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ParseFailed:
    """A regex ran out of time or memory, or the split found too many records.
    path is the JSON Pointer of the pattern in the pack."""

    pack_id: str
    path: str
    reason: FailReason


type Outcome = Parsed | Unmatched | ParseFailed


def _sent_at(value: str) -> datetime | None:
    if not value.strip():
        return None
    try:
        sent = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError, OverflowError):
        return None
    return sent if sent.utcoffset() is not None else sent.replace(tzinfo=UTC)


def mail_from_raw(raw: bytes) -> Mail:
    """The Mail of a stored message (RFC 822 bytes, at most 5 MB)."""
    headers = mime.parse_headers(raw)
    body, _cut = mime.message_text(raw)
    return Mail(
        sender=mime.header_value(headers.get("From", "")),
        to=mime.header_value(headers.get("To", "")),
        subject=mime.header_value(headers.get("Subject", "")),
        body=body,
        sent_at=_sent_at(mime.header_value(headers.get("Date", ""))),
    )


class _Stopped(Exception):
    def __init__(self, path: str, reason: FailReason) -> None:
        super().__init__(path)
        self.path = path
        self.reason = reason


@dataclass(slots=True)
class _Budget:
    deadline: float
    clock: Callable[[], float]

    def check(self, path: str) -> float:
        """The seconds left; _Stopped when none are."""
        left = self.deadline - self.clock()
        if left <= 0:
            raise _Stopped(path, "deadline")
        return left

    def search(
        self, pattern: regex.Pattern[str], text: str, path: str, pos: int = 0
    ) -> regex.Match[str] | None:
        left = self.check(path)
        try:
            return pattern.search(
                text, pos, concurrent=True, timeout=min(REGEX_TIMEOUT, left)
            )
        except TimeoutError:
            reason: FailReason = "timeout" if left > REGEX_TIMEOUT else "deadline"
            raise _Stopped(path, reason) from None
        except MemoryError:
            # The module caps its backtracking stack at 1 GiB.
            raise _Stopped(path, "memory") from None


def _text(mail: Mail, where: Scope) -> str:
    if where == "from":
        return mail.sender
    if where == "to":
        return mail.to
    if where == "subject":
        return mail.subject
    return mail.body


def _holds(condition: Condition, mail: Mail, budget: _Budget) -> bool:
    text = _text(mail, condition.where)
    return budget.search(condition.pattern, text, condition.path) is not None


def _score(pack: Pack, mail: Mail, budget: _Budget) -> int:
    """How many conditions of the pack match; 0 when the pack does not claim."""
    for condition in pack.match_all:
        if not _holds(condition, mail, budget):
            return 0
    hits = sum(1 for condition in pack.match_any if _holds(condition, mail, budget))
    if pack.match_any and not hits:
        return 0
    return len(pack.match_all) + hits


def _read_time(value: str, time_format: str | None) -> datetime:
    if time_format is not None:
        return datetime.strptime(value, time_format)
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return parsedate_to_datetime(value)


def _where(where: Scope, offset: int) -> tuple[int, str]:
    """The offset of a match in its span, and the span's source."""
    return (offset, "body") if where == "record" else (0, where)


@dataclass(slots=True)
class _Run:
    """One pack applied to one mail."""

    pack: Pack
    mail: Mail
    budget: _Budget
    # Matches and values outside the record are the same for every record of
    # a digest: read once.
    shared: dict[str, regex.Match[str] | None] = field(default_factory=dict)
    values: dict[str, tuple[str | None, Span | None]] = field(default_factory=dict)

    def find(
        self, pattern: regex.Pattern[str], where: Scope, record: str, path: str
    ) -> regex.Match[str] | None:
        if where == "record":
            return self.budget.search(pattern, record, path)
        if path not in self.shared:
            text = _text(self.mail, where)
            self.shared[path] = self.budget.search(pattern, text, path)
        return self.shared[path]

    def records(self) -> list[tuple[int, str]]:
        """(offset in the body, text) of every record."""
        body = self.mail.body
        if self.pack.split is None:
            return [(0, body)]
        starts: list[int] = []
        pos = 0
        while pos <= len(body):
            found = self.budget.search(self.pack.split, body, "/split/record", pos)
            if found is None:
                break
            # One start more than MAX_RECORDS: the empty match after the last
            # line break, which the filter below drops.
            if len(starts) > MAX_RECORDS:
                raise _Stopped("/split/record", "too-many-records")
            starts.append(found.start())
            # An empty match moves on by one character.
            pos = max(found.end(), found.start() + 1)
        if not starts:
            return []
        ends = [*starts[1:], len(body)]
        records = [
            (start, body[start:end]) for start, end in zip(starts, ends, strict=True)
        ]
        # Only whitespace (an empty match after the last line break) is no record.
        records = [(start, text) for start, text in records if text.strip()]
        if len(records) > MAX_RECORDS:
            raise _Stopped("/split/record", "too-many-records")
        return records

    def read(
        self,
        extractor: Extractor,
        pattern: regex.Pattern[str],
        record: tuple[int, str],
    ) -> tuple[str | None, Span | None]:
        offset, text = record
        path = f"{extractor.path}/regex"
        found = self.find(pattern, extractor.where, text, path)
        if found is None:
            return None, None
        value = found.group(extractor.group)
        if value is None:
            return None, None
        cleaned = clean_value(value)
        if not cleaned:
            return None, None
        start, end = found.span(extractor.group)
        base, source = _where(extractor.where, offset)
        # job_name, details.size, ...
        label = extractor.path.removeprefix("/extract/").replace("/", ".")
        return cleaned, Span(label, base + start, base + end, source)

    def value(
        self, extractor: Extractor, record: tuple[int, str], spans: list[Span]
    ) -> str | None:
        if extractor.pattern is None:
            # The loader only accepts a literal that clean_value keeps as it is.
            return extractor.literal
        if extractor.where == "record":
            value, span = self.read(extractor, extractor.pattern, record)
        else:
            if extractor.path not in self.values:
                read = self.read(extractor, extractor.pattern, record)
                self.values[extractor.path] = read
            value, span = self.values[extractor.path]
        if span is not None:
            spans.append(span)
        return value

    def when(self, extractor: Extractor, value: str | None) -> datetime | None:
        if value is None:
            return None
        try:
            parsed = _read_time(value, extractor.time_format)
        except (TypeError, ValueError, IndexError, OverflowError, re.error):
            # re.error: a format strptime cannot compile (the loader refuses
            # those; kept for a Pack built another way).
            return None
        if parsed.utcoffset() is not None:
            return parsed
        sent = self.mail.sent_at
        return parsed.replace(tzinfo=(sent.tzinfo if sent else None) or UTC)

    def status(self, record: tuple[int, str], spans: list[Span]) -> ResultStatus:
        offset, text = record
        for rule in self.pack.status_rules:
            found = self.find(rule.pattern, rule.where, text, rule.path)
            if found is not None:
                base, source = _where(rule.where, offset)
                start, end = found.span()
                spans.append(Span("status", base + start, base + end, source))
                return rule.status
        return "unknown"

    def result(self, record: tuple[int, str]) -> ParsedResult:
        spans: list[Span] = []
        texts: dict[str, str | None] = {}
        times: dict[str, datetime | None] = {}
        for extractor in self.pack.fields:
            value = self.value(extractor, record, spans)
            if extractor.name in TIME_FIELDS:
                times[extractor.name] = self.when(extractor, value)
            else:
                texts[extractor.name] = value
        details: dict[str, str] = {}
        for extractor in self.pack.details:
            value = self.value(extractor, record, spans)
            if value is not None:
                details[extractor.name] = value
        status = self.status(record, spans)
        return ParsedResult(
            status=status,
            job_name=texts.get("job_name"),
            client_hint=texts.get("client_hint"),
            started_at=times.get("started_at"),
            finished_at=times.get("finished_at"),
            run_id=texts.get("run_id"),
            details=details,
            spans=tuple(sorted(spans, key=lambda span: (span.source, span.start))),
        )

    def outcome(self) -> Outcome:
        try:
            records = self.records()
            if not records:
                return Unmatched("no-records", (self.pack.id,))
            results: list[ParsedResult] = []
            for record in records:
                if self.pack.split is not None:
                    # Values outside the record are cached, so a record can
                    # cost no search; the deadline still holds.
                    self.budget.check("/split/record")
                results.append(self.result(record))
        except _Stopped as stop:
            return ParseFailed(self.pack.id, stop.path, stop.reason)
        return Parsed(self.pack.id, tuple(results))


def _capped(mail: Mail) -> Mail:
    if len(mail.body) <= MAX_TEXT:
        return mail
    return replace(mail, body=mail.body[:MAX_TEXT])


def parse(
    packs: Sequence[Pack],
    mail: Mail,
    *,
    deadline: float = DEADLINE,
    clock: Callable[[], float] = time.monotonic,
) -> Outcome:
    """Let the packs claim the mail, then read it with the one that won."""
    mail = _capped(mail)
    budget = _Budget(clock() + deadline, clock)
    scores: list[tuple[int, Pack]] = []
    for pack in packs:
        try:
            score = _score(pack, mail, budget)
        except _Stopped as stop:
            return ParseFailed(pack.id, stop.path, stop.reason)
        if score:
            scores.append((score, pack))
    if not scores:
        return Unmatched("no-pack")
    best = max(score for score, _ in scores)
    winners = [pack for score, pack in scores if score == best]
    if len(winners) > 1:
        return Unmatched("tie", tuple(pack.id for pack in winners))
    return _Run(winners[0], mail, budget).outcome()


def apply(
    pack: Pack,
    mail: Mail,
    *,
    deadline: float = DEADLINE,
    clock: Callable[[], float] = time.monotonic,
) -> Outcome:
    """Read the mail with this pack, without the claim (a job's own pack, the
    test bench)."""
    budget = _Budget(clock() + deadline, clock)
    return _Run(pack, _capped(mail), budget).outcome()
