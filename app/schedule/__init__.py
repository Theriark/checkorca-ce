"""Schedule library: occurrences, deadlines and DST rules (phase C3).

Pure code under mypy strict and the 95 percent coverage gate. croniter is
imported in app/schedule/_cron.py only; the DST policy (rnd-report-2 5.5) is
app/schedule/_wall.py.
"""

from app.schedule.spec import (
    SCHEDULE_KINDS,
    ScheduleError,
    ScheduleKind,
    ScheduleSpec,
    check_timezone,
    parse_spec,
)
from app.schedule.times import (
    MAX_OCCURRENCES,
    NEXT_HORIZON,
    TooManyOccurrences,
    deadline,
    next_n,
    occurrences,
)

__all__ = [
    "MAX_OCCURRENCES",
    "NEXT_HORIZON",
    "SCHEDULE_KINDS",
    "ScheduleError",
    "ScheduleKind",
    "ScheduleSpec",
    "TooManyOccurrences",
    "check_timezone",
    "deadline",
    "next_n",
    "occurrences",
    "parse_spec",
]
