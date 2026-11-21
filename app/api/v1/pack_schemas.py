"""Request and response bodies of the packs and Unmatched routes (C5).

Field names follow the Interfaces chapter of the dev-work-plan (Packs and
Unmatched, ParsedResult). Mail text and extracted values are plain strings
for the web app to show escaped, never as HTML.
"""

import uuid
from datetime import datetime
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.api.v1.job_schemas import (
    AttributionBasis,
    Expression,
    JobKind,
    JobOut,
    MatchKey,
    Minutes,
    Name,
    PackId,
    RuntimeMinutes,
    Threshold,
    WarningPolicy,
    ZoneName,
)
from app.api.v1.schemas import Body
from app.ingest.results import ResultStatus
from app.matcher import Basis
from app.parsers.loader import MAX_PACK_BYTES
from app.schedule import ScheduleKind

PackSource = Literal["builtin", "custom"]
PackStatus = Literal["verified", "unverified-synthetic"]
BenchOutcome = Literal["parsed", "unmatched", "error"]

# A pasted mail for the test bench (the store takes 5 MB; a sample is less).
MAX_TEST_MAIL: Final = 1024 * 1024
# JSON bodies of the pack routes (app/api/middleware.py lets them through):
# the text escaped (at most six bytes a character for control characters)
# and the field names.
MAX_PACK_BODY: Final = 6 * MAX_PACK_BYTES + 1024
MAX_TEST_BODY: Final = 6 * (MAX_TEST_MAIL + MAX_PACK_BYTES) + 1024


class PackOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version: int
    vendor: str
    status: PackStatus
    # builtin: shipped with Checkorca-CE, read-only; custom: saved by a user.
    source: PackSource
    enabled: bool
    created_at: datetime
    updated_at: datetime


class PackDetail(PackOut):
    # The Pack YAML (docs/parsers.md).
    yaml: str


class PackPage(BaseModel):
    items: list[PackOut]
    next_cursor: str | None


class PackBody(Body):
    """A custom pack as Pack YAML; its id must be the id in the URL."""

    yaml: Annotated[str, Field(min_length=1, max_length=MAX_PACK_BYTES)]


class PackTestRequest(Body):
    """A mail (RFC 822 text as pasted) and, optionally, the Pack YAML being
    edited, which takes the place of the stored pack with its id."""

    raw: Annotated[str, Field(min_length=1, max_length=MAX_TEST_MAIL)]
    pack: Annotated[str, Field(min_length=1, max_length=MAX_PACK_BYTES)] | None = None


class BenchMail(BaseModel):
    """The mail as the engine reads it: decoded headers and the visible text
    (HTML as text, at most 256 KiB). Span offsets point into these."""

    sender: str
    to: str
    subject: str
    body: str
    sent_at: datetime | None


class BenchScore(BaseModel):
    pack_id: str
    # How many match conditions of the pack hold; 0: the pack does not claim.
    matched: int


class BenchSpan(BaseModel):
    """Characters start to end of source (body, subject, from or to) hold the
    value of field (job_name, details.size, status, ...)."""

    field: str
    start: int
    end: int
    source: str


class BenchResult(BaseModel):
    status: ResultStatus
    job_name: str | None
    client_hint: str | None
    started_at: datetime | None
    finished_at: datetime | None
    run_id: str | None
    details: dict[str, str]
    spans: list[BenchSpan]


class PackTestAnswer(BaseModel):
    """What the packs make of the mail.

    claimed_by: the pack that claims the mail among the enabled packs (with
    the edited one), null for no claim or a tie. outcome: parsed (results of
    pack_id: the edited pack when one was sent, else the claiming pack),
    unmatched (reason no-pack, tie with the candidates, or no-records) or
    error (reason timeout, deadline, too-many-records or memory, at path).
    skipped: stored packs that no longer load and were left out.
    """

    mail: BenchMail
    scores: list[BenchScore]
    claimed_by: str | None
    outcome: BenchOutcome
    pack_id: str | None
    reason: str | None
    path: str | None
    candidates: list[str]
    results: list[BenchResult]
    skipped: list[str]


class UnmatchedOut(BaseModel):
    """A result no job is bound to yet."""

    result_id: uuid.UUID
    raw_message_id: uuid.UUID | None
    received_at: datetime
    job_name: str | None
    client_hint: str | None
    status: ResultStatus


class UnmatchedPage(BaseModel):
    items: list[UnmatchedOut]
    next_cursor: str | None


class AssignRequest(Body):
    job_id: uuid.UUID


class Binding(BaseModel):
    """The result is bound to job_id. match_key_set: the job had no match key
    and now has the result's job name; alias_added: the result's client hint
    became an alias of the client. Both make the next identical mail bind.
    also_bound: other unmatched results with the same names bound as well."""

    result_id: uuid.UUID
    job_id: uuid.UUID
    client_id: uuid.UUID
    match_key_set: bool
    alias_added: bool
    also_bound: int


class CreateJobRequest(Body):
    """A job made from an unmatched result, for an existing client (client_id)
    or a client by name (client_name: found, or created). name defaults to the
    result's job name and match_key to it as well. Without schedule_kind and
    schedule_expr the job runs daily at the time suggest-schedule gives (from
    one result on); timezone defaults to the digest time zone of Settings."""

    client_id: uuid.UUID | None = None
    client_name: Name | None = None
    name: Name | None = None
    kind: JobKind = "backup"
    parser_pack_id: PackId | None = None
    match_key: MatchKey | None = None
    schedule_kind: ScheduleKind | None = None
    schedule_expr: Expression | None = None
    timezone: ZoneName | None = None
    max_runtime_minutes: RuntimeMinutes = 360
    grace_minutes: Minutes = 120
    escalate_minutes: Minutes = 30
    attribution_basis: AttributionBasis = "finished"
    warning_policy: WarningPolicy = "warning_is_attention"
    consecutive_failures_to_alert: Threshold = 1
    enabled: bool = True

    @model_validator(mode="after")
    def _one_client_and_a_whole_schedule(self) -> Self:
        if (self.client_id is None) == (self.client_name is None):
            raise ValueError("send client_id or client_name")
        if (self.schedule_kind is None) != (self.schedule_expr is None):
            raise ValueError("send schedule_kind and schedule_expr together")
        return self


class JobFromResult(BaseModel):
    job: JobOut
    client_created: bool
    binding: Binding


class ScheduleSuggestion(BaseModel):
    """A daily schedule at the median time of the job's runs: expr is HH:MM in
    timezone; basis is the time read of each run; results how many runs."""

    kind: Literal["daily"]
    expr: str
    timezone: str
    basis: Basis
    results: int
