"""ParsedResult: one run as the parser engine, the results API and the ping
URLs describe it (Interfaces chapter: engine, ingest, matcher)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Literal

ResultStatus = Literal["success", "warning", "failed", "started", "unknown"]
RESULT_STATUSES: Final[tuple[ResultStatus, ...]] = (
    "success",
    "warning",
    "failed",
    "started",
    "unknown",
)


@dataclass(frozen=True, slots=True)
class Span:
    """Where an extracted field was found in the text (test bench only)."""

    field: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ParsedResult:
    """A run of a job: who reported it, how it ended and when.

    job_name and client_hint are what the message says; the matcher (phase C5)
    turns them into a job. Unknown never counts as success.
    """

    status: ResultStatus
    job_name: str | None = None
    client_hint: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    run_id: str | None = None
    details: Mapping[str, Any] = field(default_factory=dict)
    spans: tuple[Span, ...] = ()
