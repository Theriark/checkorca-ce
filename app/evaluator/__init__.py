"""Evaluator: occurrences, attribution, the state machine and flips (C7).

model.py and machine.py are pure (no clock, no database); tick.py is the
worker hook that reads and writes the tables. Under mypy strict and the 95
percent coverage gate. docs/evaluator.md describes the rules.

tick.py is not imported here: the database models import model.py, and tick
imports the models.
"""

from app.evaluator.machine import (
    ATTRIBUTION_SLACK,
    LOOKAHEAD,
    WINDOW,
    derive_state,
    evaluate,
    occurrence_outcome,
)
from app.evaluator.model import (
    CLOSED_STATES,
    JOB_STATES,
    OCCURRENCE_STATES,
    OPEN_STATES,
    SILENT_STATES,
    Evaluation,
    FlipDraft,
    JobRules,
    JobState,
    MaintenanceWindow,
    Occurrence,
    OccurrenceState,
    Result,
    StateRecord,
)

__all__ = [
    "ATTRIBUTION_SLACK",
    "CLOSED_STATES",
    "JOB_STATES",
    "LOOKAHEAD",
    "OCCURRENCE_STATES",
    "OPEN_STATES",
    "SILENT_STATES",
    "WINDOW",
    "Evaluation",
    "FlipDraft",
    "JobRules",
    "JobState",
    "MaintenanceWindow",
    "Occurrence",
    "OccurrenceState",
    "Result",
    "StateRecord",
    "derive_state",
    "evaluate",
    "occurrence_outcome",
]
