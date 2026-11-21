"""The SuppressionProvider seam (rnd-report-2 5.3): planned maintenance.

The evaluator asks the provider, for a batch of jobs and a time range, when
each job is in a maintenance window. An occurrence due inside a window gets the
state maintenance: shown, never counted as verified, never missed, so planned
maintenance is visible instead of a silent gap. CE ships NoSuppression
(nothing is ever suppressed); EE adds maintenance windows. Frozen in phase
C12.

If the provider raises, the evaluator leaves the batch for the next tick
rather than evaluate without the windows (a missed alert during maintenance
would be wrong).
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.evaluator.model import MaintenanceWindow

__all__ = [
    "MaintenanceTarget",
    "MaintenanceWindow",
    "NoSuppression",
    "SuppressionProvider",
]


@dataclass(frozen=True, slots=True)
class MaintenanceTarget:
    """A job the evaluator asks about, with its client (windows may be set
    per client)."""

    job_id: uuid.UUID
    client_id: uuid.UUID


class SuppressionProvider(Protocol):
    """Tells the evaluator when jobs are in planned maintenance."""

    async def maintenance(
        self, targets: Sequence[MaintenanceTarget], start: datetime, end: datetime
    ) -> Mapping[uuid.UUID, Sequence[MaintenanceWindow]]:
        """For each job id that has any, its windows overlapping [start, end)."""
        ...


class NoSuppression:
    """CE: no job is ever in maintenance."""

    async def maintenance(
        self, targets: Sequence[MaintenanceTarget], start: datetime, end: datetime
    ) -> Mapping[uuid.UUID, Sequence[MaintenanceWindow]]:
        return {}
