"""Response bodies of the occurrence and flip routes (phase C7).

Fields follow the Interfaces chapter (Evaluation) exactly; the dashboard (C8)
and the notifications (C9) build on them. Silent means overdue or missed.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.evaluator.model import JobState, OccurrenceState


class OccurrenceOut(BaseModel):
    """One expected run of a job. note explains the state in a few words
    (recovered after retry, late result, started, never finished)."""

    model_config = ConfigDict(from_attributes=True)

    job_id: uuid.UUID
    scheduled_for: datetime
    deadline: datetime
    state: OccurrenceState
    result_id: uuid.UUID | None
    note: str | None


class OccurrencePage(BaseModel):
    items: list[OccurrenceOut]
    next_cursor: str | None


class FlipOut(BaseModel):
    """One change of a job's state; the single source of alerts."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    client_id: uuid.UUID
    from_state: JobState
    to_state: JobState
    reason: str
    at: datetime


class FlipPage(BaseModel):
    items: list[FlipOut]
    next_cursor: str | None
