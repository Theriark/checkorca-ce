"""Token-bucket rate limits, kept in memory by the web process.

Each key (a client address or a token id) has a bucket of `capacity` requests
that refills evenly over `per_seconds`. Development, Stage and the compose
install run one web process, so a process-local table is enough. The table is
bounded: past `max_keys` the least recently used bucket is dropped.
"""

from collections import OrderedDict
from dataclasses import dataclass

from app.clock import Clock

MAX_KEYS = 10_000


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    """capacity requests per per_seconds for each key."""

    def __init__(
        self,
        capacity: int,
        per_seconds: float,
        clock: Clock,
        max_keys: int = MAX_KEYS,
    ) -> None:
        if capacity < 1 or per_seconds <= 0:
            raise ValueError("capacity and per_seconds must be positive")
        self.capacity = capacity
        self.per_seconds = per_seconds
        self._clock = clock
        self._max_keys = max_keys
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()

    def hit(self, key: str) -> float:
        """Take one request: 0.0 when allowed, else the seconds to wait."""
        now = self._clock.monotonic()
        bucket = self._buckets.pop(key, None)
        if bucket is None:
            bucket = _Bucket(tokens=float(self.capacity), updated=now)
        else:
            refill = (now - bucket.updated) * self.capacity / self.per_seconds
            bucket.tokens = min(float(self.capacity), bucket.tokens + refill)
            bucket.updated = now
        self._buckets[key] = bucket
        while len(self._buckets) > self._max_keys:
            self._buckets.popitem(last=False)
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return 0.0
        return (1.0 - bucket.tokens) * self.per_seconds / self.capacity
