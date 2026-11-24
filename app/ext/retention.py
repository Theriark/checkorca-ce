"""The RetentionPolicy seam (rnd-report-2 5.3): how long data is kept.

The retention purge (app/ops/retention.py) asks the policy for the cutoffs of
one run. raw_before is the moment a raw message's purge_after must precede
(purge_after is received_at plus settings.retention_raw_days, written at
ingest, docs/ingest.md); results_before and audit_before are the ages a result
and an audit event must not pass (received_at and at). CE ships
RetainBySettings, which reads the three retention settings of the settings row
(30, 90 and 365 days); EE can hold data longer (a legal hold answers with no
cutoff at all). Frozen in phase C12.

The policy decides only the three cutoffs. What a purge must always keep is
not a policy: open occurrences, each job's newest closed occurrence and the
newest consecutive_failures_to_alert closed ones that are not maintenance,
which the job state still reads (docs/evaluator.md).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from app.db.models import AppSettings

__all__ = ["Retention", "RetainBySettings", "RetentionPolicy"]


@dataclass(frozen=True, slots=True)
class Retention:
    """The cutoffs of one purge. None means no row of that kind is purged,
    however old it is."""

    raw_before: datetime | None
    results_before: datetime | None
    audit_before: datetime | None


def _cutoff(now: datetime, days: int) -> datetime:
    """now minus days; a setting of zero or less keeps everything."""
    return now if days <= 0 else now - timedelta(days=days)


class RetentionPolicy(Protocol):
    """The retention settings of one purge run."""

    def plan(self, row: AppSettings, now: datetime) -> Retention:
        """The cutoffs a purge at now uses for the settings row."""
        ...


class RetainBySettings:
    """CE: the retention settings of the settings row (30, 90 and 365 days).
    Raw messages go by their own purge_after (the setting of the day they
    arrived); occurrences, flips and notifications follow the results
    cutoff."""

    def plan(self, row: AppSettings, now: datetime) -> Retention:
        return Retention(
            raw_before=now if row.retention_raw_days > 0 else None,
            results_before=_cutoff(now, row.retention_results_days),
            audit_before=_cutoff(now, row.retention_audit_days),
        )
