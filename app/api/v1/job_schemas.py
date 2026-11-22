"""Request and response bodies of the clients, jobs and schedule routes (C3).

Field names and defaults follow the Interfaces chapter of the dev-work-plan.
Times go out as ISO 8601 in UTC.
"""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from app.api.v1.schemas import Body
from app.db.models import NAME_LENGTH, name_key
from app.repos.jobs import JobState
from app.schedule import ScheduleKind

JobKind = Literal["backup", "script", "other"]
AttributionBasis = Literal["started", "finished", "received"]
WarningPolicy = Literal["warning_is_attention", "warning_counts_ok"]

MAX_NOTES_LENGTH = 4000
MAX_ALIASES = 50
MAX_MINUTES = 7 * 24 * 60
EARLIEST_TIME = datetime(1970, 1, 1, tzinfo=UTC)
LATEST_TIME = datetime(2200, 1, 1, tzinfo=UTC)


def clean_name(value: str) -> str:
    """Inner runs of spaces become one space; control characters are refused."""
    name = " ".join(value.split())
    if any(ord(character) < 32 or ord(character) == 127 for character in name):
        raise ValueError("must not contain control characters")
    if not name:
        raise ValueError("must not be empty")
    # Case folding can lengthen a name (ß becomes ss); the key has the same column.
    if len(name_key(name)) > NAME_LENGTH:
        raise ValueError(f"must be at most {NAME_LENGTH} characters when case folded")
    return name


def plausible_time(value: datetime) -> datetime:
    """A time between 1970 and 2200; the schedule library works on such times."""
    if not EARLIEST_TIME <= value <= LATEST_TIME:
        raise ValueError("must be between 1970 and 2200")
    return value


def unique_aliases(values: list[str]) -> list[str]:
    """Aliases without repeats (ignoring case and spacing), in the given order."""
    seen: set[str] = set()
    kept: list[str] = []
    for value in values:
        key = name_key(value)
        if key not in seen:
            seen.add(key)
            kept.append(value)
    return kept


Name = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_LENGTH),
    AfterValidator(clean_name),
]
Notes = Annotated[str, Field(max_length=MAX_NOTES_LENGTH)]
Aliases = Annotated[
    list[Name], Field(max_length=MAX_ALIASES), AfterValidator(unique_aliases)
]
MatchKey = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=NAME_LENGTH)
]
# A parser pack id such as generic-keywords or veeam-br (phase C5).
PackId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$"
    ),
]
Expression = Annotated[str, Field(min_length=1, max_length=200)]
ZoneName = Annotated[str, Field(min_length=1, max_length=64)]
RuntimeMinutes = Annotated[int, Field(ge=1, le=MAX_MINUTES)]
Minutes = Annotated[int, Field(ge=0, le=MAX_MINUTES)]
Threshold = Annotated[int, Field(ge=1, le=100)]
PlausibleTime = Annotated[AwareDatetime, AfterValidator(plausible_time)]


class NewClient(Body):
    name: Name
    notes: Notes = ""
    aliases: Aliases = []


class ClientPatch(Body):
    """Only the fields sent change."""

    name: Name | None = None
    notes: Notes | None = None
    aliases: Aliases | None = None
    archived: bool | None = None


class ClientOut(BaseModel):
    id: uuid.UUID
    name: str
    notes: str
    aliases: list[str]
    archived: bool
    created_at: datetime
    # Jobs that are not archived, and how many are in each state.
    job_count: int
    status_counts: dict[JobState, int]
    worst_state: JobState | None


class ClientPage(BaseModel):
    items: list[ClientOut]
    next_cursor: str | None


class JobSettings(Body):
    """What a job does and when it should report (defaults of rnd-report-2)."""

    kind: JobKind = "backup"
    parser_pack_id: PackId | None = None
    match_key: MatchKey | None = None
    schedule_kind: ScheduleKind
    schedule_expr: Expression
    timezone: ZoneName
    max_runtime_minutes: RuntimeMinutes = 360
    grace_minutes: Minutes = 120
    escalate_minutes: Minutes = 30
    attribution_basis: AttributionBasis = "finished"
    warning_policy: WarningPolicy = "warning_is_attention"
    consecutive_failures_to_alert: Threshold = 1


class NewJob(JobSettings):
    client_id: uuid.UUID
    name: Name
    enabled: bool = True


class JobPatch(Body):
    """Only the fields sent change; null clears parser_pack_id and match_key."""

    client_id: uuid.UUID | None = None
    name: Name | None = None
    kind: JobKind | None = None
    parser_pack_id: PackId | None = None
    match_key: MatchKey | None = None
    schedule_kind: ScheduleKind | None = None
    schedule_expr: Expression | None = None
    timezone: ZoneName | None = None
    max_runtime_minutes: RuntimeMinutes | None = None
    grace_minutes: Minutes | None = None
    escalate_minutes: Minutes | None = None
    attribution_basis: AttributionBasis | None = None
    warning_policy: WarningPolicy | None = None
    consecutive_failures_to_alert: Threshold | None = None
    enabled: bool | None = None
    archived: bool | None = None


class AcknowledgedBy(BaseModel):
    """Who acknowledged the job's state. email is null for an API token: only
    signed-in users see addresses."""

    id: uuid.UUID
    email: str | None


class JobOut(BaseModel):
    """A job; its state is paused or unknown until the evaluator keeps it (C7)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    client_name: str
    name: str
    kind: JobKind
    parser_pack_id: str | None
    match_key: str | None
    schedule_kind: ScheduleKind
    schedule_expr: str
    timezone: str
    max_runtime_minutes: int
    grace_minutes: int
    escalate_minutes: int
    attribution_basis: AttributionBasis
    warning_policy: WarningPolicy
    consecutive_failures_to_alert: int
    # Null for an API token: the ping URL is shown to signed-in users only.
    ping_url: str | None
    enabled: bool
    paused_until: datetime | None
    archived: bool
    state: JobState
    state_since: datetime | None
    last_success_at: datetime | None
    acknowledged_at: datetime | None
    # Addition (C9-B): who acknowledged; null when nobody did (or the user
    # was deleted). Always sent; optional in the document so clients built
    # before C9-B keep compiling.
    acknowledged_by: AcknowledgedBy | None = None
    created_at: datetime
    updated_at: datetime


class JobPage(BaseModel):
    items: list[JobOut]
    next_cursor: str | None


class PauseRequest(Body):
    """Without until the job stays paused until it is resumed."""

    until: AwareDatetime | None = None


class SchedulePreviewRequest(Body):
    kind: ScheduleKind
    expr: Expression
    timezone: ZoneName
    count: Annotated[int, Field(ge=1, le=20)] = 5
    # The start of an interval schedule; the job's creation time, else now.
    anchor: PlausibleTime | None = None
    # The times listed are after this; default now.
    after: PlausibleTime | None = None


class SchedulePreview(BaseModel):
    """The next times, or why the schedule cannot be used (error and field)."""

    next: list[datetime]
    # The same times in the schedule's zone, with their UTC offset.
    local: list[str]
    error: str | None
    field: str | None


class ImportProblem(BaseModel):
    """A row that was not imported. Row 1 is the header line."""

    row: int
    message: str


class ImportResult(BaseModel):
    created: int
    updated: int
    clients_created: int
    errors: list[ImportProblem]
    # True: nothing was saved; the counts say what an import would do.
    dry_run: bool
