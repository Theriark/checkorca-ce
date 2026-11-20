"""A parser pack as the engine uses it: the Pack YAML of the Interfaces chapter,
validated and with every regex compiled (app/parsers/loader.py builds it).

Paths are JSON Pointers into the pack document, so an error or a timeout can
name the pattern it came from (/status_rules/2/regex).
"""

from dataclasses import dataclass
from typing import Final, Literal

import regex

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
