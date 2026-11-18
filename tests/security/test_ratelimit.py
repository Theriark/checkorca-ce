"""Token-bucket rate limits on the injected clock."""

import pytest

from app.security.ratelimit import RateLimiter
from helpers import FakeClock


def test_a_burst_up_to_the_capacity_then_a_wait() -> None:
    clock = FakeClock()
    limiter = RateLimiter(3, 30.0, clock=clock)
    assert [limiter.hit("192.0.2.1") for _ in range(3)] == [0.0, 0.0, 0.0]
    assert limiter.hit("192.0.2.1") == 10.0
    # Other keys have their own bucket.
    assert limiter.hit("192.0.2.2") == 0.0
    clock.advance(seconds=5)
    assert limiter.hit("192.0.2.1") == 5.0
    clock.advance(seconds=5)
    assert limiter.hit("192.0.2.1") == 0.0


def test_a_bucket_never_holds_more_than_the_capacity() -> None:
    clock = FakeClock()
    limiter = RateLimiter(2, 10.0, clock=clock)
    limiter.hit("key")
    clock.advance(hours=1)
    assert [limiter.hit("key") for _ in range(2)] == [0.0, 0.0]
    assert limiter.hit("key") > 0


def test_the_table_is_bounded() -> None:
    clock = FakeClock()
    limiter = RateLimiter(1, 60.0, clock=clock, max_keys=2)
    limiter.hit("a")
    limiter.hit("b")
    limiter.hit("c")
    # "a" was the least recently used bucket and was dropped: it starts full.
    assert limiter.hit("a") == 0.0
    assert limiter.hit("c") > 0


@pytest.mark.parametrize(("capacity", "per_seconds"), [(0, 60.0), (5, 0.0)])
def test_invalid_limits(capacity: int, per_seconds: float) -> None:
    with pytest.raises(ValueError):
        RateLimiter(capacity, per_seconds, clock=FakeClock())
