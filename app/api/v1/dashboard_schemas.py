"""Response bodies of the Morning check (phase C8-B): dashboard/today,
ribbon, trend and breakdown, activity and digest/preview.

Fields follow the Interfaces chapter (Dashboard); docs/dashboard.md defines
every number. Additions beyond the chapter are marked: the frontend may use
them, nothing depends on them.
"""

import datetime as dt
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.evaluator.model import OccurrenceState

AttentionState = Literal["missed", "overdue", "failed", "warning"]
ActivityKindOut = Literal["ingest", "flip", "notification", "config"]
BreakdownByOut = Literal["vendor", "client"]


class Stat(BaseModel):
    """One stat card: value now, its change against 24 hours earlier, and the
    14 values of the last 14 days, oldest first (the last one is value)."""

    value: int
    delta_vs_yesterday: int
    spark14: list[int]


class Stats(BaseModel):
    verified: Stat
    failed: Stat
    silent: Stat
    unmatched: Stat
    paused: Stat


class Coverage(BaseModel):
    """Due runs of the last 24 hours that were verified; ratio is null when
    none was due."""

    verified: int
    expected: int
    ratio: float | None


class AttentionItem(BaseModel):
    """A job that needs a look. expected_by is the deadline of its newest due
    run; raw_message_id the message of the result that decided that run (none
    for a silent run or a ping)."""

    client_id: uuid.UUID
    client_name: str
    job_id: uuid.UUID
    job_name: str
    state: AttentionState
    expected_by: dt.datetime | None
    last_success_at: dt.datetime | None
    raw_message_id: uuid.UUID | None
    # Addition: set while someone acknowledged the job's state.
    acknowledged_at: dt.datetime | None


class HeartbeatOut(BaseModel):
    """The worker heartbeat; stale when older than 3 minutes or missing."""

    at: dt.datetime | None
    age_seconds: float | None
    stale: bool


class DashboardToday(BaseModel):
    generated_at: dt.datetime
    stats: Stats
    coverage: Coverage
    attention: list[AttentionItem]
    heartbeat: HeartbeatOut
    demo_seeded: bool


class RibbonWindow(BaseModel):
    """[from, to): build it with model_validate({"from": ..., "to": ...})."""

    model_config = ConfigDict(populate_by_name=True)

    start: dt.datetime = Field(alias="from")
    to: dt.datetime


class RibbonOccurrence(BaseModel):
    """One run: pending ones after now are still expected. result_at is when
    the deciding result says the run ended (finished, else received)."""

    scheduled_for: dt.datetime
    deadline: dt.datetime
    state: OccurrenceState
    result_at: dt.datetime | None


class RibbonJob(BaseModel):
    id: uuid.UUID
    name: str
    occurrences: list[RibbonOccurrence]


class RibbonClient(BaseModel):
    id: uuid.UUID
    name: str
    jobs: list[RibbonJob]


class Ribbon(BaseModel):
    """The Night Ribbon: clients by name, their jobs by name, each job's runs
    in the window by time. morning_line_at is the digest time in the window
    (null when the window holds none)."""

    window: RibbonWindow
    morning_line_at: dt.datetime | None
    clients: list[RibbonClient]


class TrendDay(BaseModel):
    """Due runs of one calendar day in the digest zone."""

    date: dt.date
    verified: int
    failed: int
    silent: int


class Trend(BaseModel):
    """Oldest day first; the last day is today (so far)."""

    items: list[TrendDay]


class BreakdownItem(BaseModel):
    """key: the parser pack id (none for jobs without a pack) or the client
    id; label: the pack's vendor or the client's name."""

    key: str
    label: str
    verified: int
    failed: int
    silent: int


class Breakdown(BaseModel):
    by: BreakdownByOut
    items: list[BreakdownItem]


class ActivityItem(BaseModel):
    """One entry of the timeline. ref_kind and ref_id point to what it is
    about (job, message, or the target of a configuration change)."""

    # Addition: a stable key for lists.
    id: uuid.UUID
    at: dt.datetime
    kind: ActivityKindOut
    summary: str
    ref_kind: str | None
    ref_id: str | None


class ActivityPage(BaseModel):
    items: list[ActivityItem]
    next_cursor: str | None


class DigestPreview(BaseModel):
    """The morning digest of date as it would be sent."""

    # Addition: the day previewed.
    date: dt.date
    subject: str
    html: str
    text: str
