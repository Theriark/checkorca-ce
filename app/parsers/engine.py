"""The parser engine: which pack claims a mail, and the results it reads.

Pure and synchronous. C5-B calls parse() from the worker's parse hook in a
thread (asyncio.to_thread; the regex module releases the GIL while it
matches) and the test bench of C5-F calls apply() on a pasted sample.

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
- all evaluations for one mail share DEADLINE seconds, and a split may give at
  most MAX_RECORDS records.

A timeout fails the whole mail (ParseFailed names the pattern). It never lets
a later status rule or a weaker pack decide instead: a failed rule that timed
out must not turn into success.
"""

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Final, Literal

import regex

from app.ingest import mime
from app.ingest.results import ParsedResult, ResultStatus, Span
from app.parsers.model import TIME_FIELDS, Condition, Extractor, Pack, Scope

REGEX_TIMEOUT: Final = 0.05
DEADLINE: Final = 5.0
MAX_TEXT: Final = mime.MAX_TEXT
MAX_RECORDS: Final = 200
# record_result refuses names, hints and run ids over 200 characters; 16
# details of at most 200 characters stay under its 16 KiB.
MAX_VALUE: Final = 200

UnmatchedReason = Literal["no-pack", "tie", "no-records"]
FailReason = Literal["timeout", "deadline", "too-many-records"]

# Control characters other than tab and line feed; JSON would escape each
# into six bytes.
_CONTROL = regex.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


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
    """A regex ran out of time, or the split found too many records. path is
    the JSON Pointer of the pattern in the pack."""

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

    def search(
        self, pattern: regex.Pattern[str], text: str, path: str, pos: int = 0
    ) -> regex.Match[str] | None:
        left = self.deadline - self.clock()
        if left <= 0:
            raise _Stopped(path, "deadline")
        try:
            return pattern.search(
                text, pos, concurrent=True, timeout=min(REGEX_TIMEOUT, left)
            )
        except TimeoutError:
            reason: FailReason = "timeout" if left > REGEX_TIMEOUT else "deadline"
            raise _Stopped(path, reason) from None


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


def _clean(value: str) -> str:
    text = _CONTROL.sub(" ", mime.clean_text(value))
    return " ".join(text.split())[:MAX_VALUE]


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
    # Matches outside the record are the same for every record of a digest.
    shared: dict[str, regex.Match[str] | None] = field(default_factory=dict)

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
            if len(starts) == MAX_RECORDS:
                raise _Stopped("/split/record", "too-many-records")
            starts.append(found.start())
            # An empty match moves on by one character.
            pos = max(found.end(), found.start() + 1)
        if not starts:
            return []
        ends = [*starts[1:], len(body)]
        return [
            (start, body[start:end]) for start, end in zip(starts, ends, strict=True)
        ]

    def value(
        self, extractor: Extractor, record: tuple[int, str], spans: list[Span]
    ) -> str | None:
        if extractor.pattern is None:
            return extractor.literal
        offset, text = record
        path = f"{extractor.path}/regex"
        found = self.find(extractor.pattern, extractor.where, text, path)
        if found is None:
            return None
        value = found.group(extractor.group)
        if value is None:
            return None
        cleaned = _clean(value)
        if not cleaned:
            return None
        start, end = found.span(extractor.group)
        base, source = _where(extractor.where, offset)
        # job_name, details.size, ...
        label = extractor.path.removeprefix("/extract/").replace("/", ".")
        spans.append(Span(label, base + start, base + end, source))
        return cleaned

    def when(self, extractor: Extractor, value: str | None) -> datetime | None:
        if value is None:
            return None
        try:
            parsed = _read_time(value, extractor.time_format)
        except (TypeError, ValueError, IndexError, OverflowError):
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
            results = tuple(self.result(record) for record in records)
        except _Stopped as stop:
            return ParseFailed(self.pack.id, stop.path, stop.reason)
        return Parsed(self.pack.id, results)


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
