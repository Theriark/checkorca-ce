"""A parser pack as the engine uses it: the Pack YAML of the Interfaces chapter,
validated and with every regex compiled (app/parsers/loader.py builds it).

Paths are JSON Pointers into the pack document, so an error or a timeout can
name the pattern it came from (/status_rules/2/regex).
"""

from dataclasses import dataclass
from typing import Final, Literal

import regex

from app.ingest import mime
from app.ingest.results import ResultStatus

# A match condition reads a header or the body.
Header = Literal["from", "to", "subject", "body"]
# An extract field or a status rule also reads the record (the default): the
# part of the body a split found, or the whole body without split.
Scope = Literal["record", "body", "subject", "from", "to"]
PackStatus = Literal["verified", "unverified-synthetic"]
FixtureOrigin = Literal["synthetic", "real"]
FixtureClass = Literal[
    "success", "warning", "failed", "started", "unknown", "digest", "unmatched"
]
# The ParsedResult fields an extract section may fill, besides details.
FIELDS: Final = ("job_name", "client_hint", "run_id", "started_at", "finished_at")
TIME_FIELDS: Final = frozenset({"started_at", "finished_at"})
# record_result refuses names, hints and run ids over 200 characters; 16
# details of at most 200 characters stay under its 16 KiB.
MAX_VALUE: Final = 200

# Control characters other than tab and line feed; JSON would escape each
# into six bytes.
_CONTROL = regex.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def clean_value(value: str) -> str:
    """A value as a result keeps it: NUL, control characters and invalid text
    removed, whitespace collapsed, at most MAX_VALUE characters. Only the first
    8 times MAX_VALUE characters are read, so a long match costs little."""
    text = _CONTROL.sub(" ", mime.clean_text(value[: MAX_VALUE * 8]))
    return " ".join(text.split())[:MAX_VALUE]


@dataclass(frozen=True, slots=True)
class Condition:
    where: Header
    pattern: regex.Pattern[str]
    path: str


@dataclass(frozen=True, slots=True)
class Extractor:
    """One value of a result: the text of the regex's only named group, or a
    literal. time_format is a strptime format for started_at and finished_at."""

    name: str
    path: str
    pattern: regex.Pattern[str] | None = None
    group: str = ""
    where: Scope = "record"
    literal: str | None = None
    time_format: str | None = None


@dataclass(frozen=True, slots=True)
class StatusRule:
    status: ResultStatus
    pattern: regex.Pattern[str]
    where: Scope
    path: str


@dataclass(frozen=True, slots=True)
class FixtureRef:
    name: str
    origin: FixtureOrigin
    kind: FixtureClass


@dataclass(frozen=True, slots=True)
class Pack:
    id: str
    version: int
    vendor: str
    status: PackStatus
    docs_url: str | None
    match_all: tuple[Condition, ...]
    match_any: tuple[Condition, ...]
    split: regex.Pattern[str] | None
    fields: tuple[Extractor, ...]
    details: tuple[Extractor, ...]
    status_rules: tuple[StatusRule, ...]
    fixtures: tuple[FixtureRef, ...] = ()
