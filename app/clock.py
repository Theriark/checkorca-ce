"""The clock every time rule reads, so tests can move time (lockout, sessions)."""

import time
from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    """Wall time for stored timestamps, monotonic time for rate limits."""

    def now(self) -> datetime:
        """The current time, timezone-aware in UTC."""
        ...

    def monotonic(self) -> float:
        """Seconds from an arbitrary start that never go back."""
        ...


class SystemClock:
    """The real clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()
