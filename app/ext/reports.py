"""The ReportRenderer seam (rnd-report-2 5.3): how the morning digest reads.

app/notify/digest.py collects the numbers of a digest from the database (a
Digest); a ReportRenderer turns them into a subject, an HTML body and a text
body. CE ships DigestRenderer (app/notify/digest.py): inline-styled HTML
without script or remote content, every name escaped. EE can brand or
translate the digest without touching the numbers. digest/preview (phase
C8-B) and the daily digest e-mail (phase C9) use the same renderer. Frozen in
phase C12.
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DigestItem:
    """A job whose newest due run in the window needs a look. state is the
    run's state: missed, overdue, failed or warning."""

    client: str
    job: str
    state: str
    scheduled_for: datetime
    deadline: datetime
    note: str | None = None


@dataclass(frozen=True, slots=True)
class Digest:
    """The numbers of one morning digest.

    The window [start, end) is the 24 hours (local) up to the digest time of
    day. The counts are due runs of live jobs in it: verified, warning,
    failed and silent (overdue or missed); expected is their sum. items lists
    jobs, silent first, then failed, then warning; more_items says how many
    more were left out. url is the Morning check of the site.
    """

    day: date
    timezone: str
    start: datetime
    end: datetime
    generated_at: datetime
    verified: int
    warning: int
    failed: int
    silent: int
    items: tuple[DigestItem, ...]
    more_items: int
    url: str

    @property
    def expected(self) -> int:
        return self.verified + self.warning + self.failed + self.silent


@dataclass(frozen=True, slots=True)
class RenderedReport:
    """What a renderer makes of a digest: ready to send or preview."""

    subject: str
    html: str
    text: str


class ReportRenderer(Protocol):
    """Turns a digest into its subject and bodies."""

    def render(self, digest: Digest) -> RenderedReport:
        """Pure: no I/O, the same digest gives the same report. The HTML must
        not contain script, and every text from the database is escaped."""
        ...
