"""Spike 4: the regex package stops a runaway pattern after 50 ms.

The parser engine of phase C5-I runs pack patterns, which users can edit, with
timeout=0.05. The pattern below backtracks quadratically over a 1,000,003
character subject (a prime length, so it never matches) and its backreference
leaves the engine nothing to memoise, so only the timeout can stop it. After a
timeout the process keeps matching normally.
"""

import time
from collections.abc import Callable
from importlib.metadata import version

import pytest
import regex

TIMEOUT = 0.05
# Generous for a loaded CI runner; without the timeout the search runs for hours.
BOUND = 1.0

RUNAWAY = regex.compile(r"^(11+?)\1+$")
SUBJECT = "1" * 1_000_003
# The textbook catastrophic pattern for backtracking engines.
NESTED = regex.compile(r"^(a+)+$")
NESTED_SUBJECT = "a" * 40 + "!"


def test_runaway_pattern_is_stopped_by_the_timeout(
    report: Callable[..., None],
) -> None:
    elapsed: list[float] = []
    for _ in range(3):
        started = time.perf_counter()
        with pytest.raises(TimeoutError):
            RUNAWAY.search(SUBJECT, timeout=TIMEOUT)
        elapsed.append(time.perf_counter() - started)
    assert max(elapsed) < BOUND

    # The process keeps working: the same pattern on a composite length matches.
    assert RUNAWAY.search("1" * 1001, timeout=TIMEOUT) is not None
    assert regex.search(r"Result:\s+(\w+)", "Result: Success", timeout=TIMEOUT)
    report(
        "regex-timeout",
        version=version("regex"),
        timeout_ms=TIMEOUT * 1000,
        stopped_after_ms="/".join(f"{seconds * 1000:.1f}" for seconds in elapsed),
    )


def test_nested_quantifier_finishes_within_the_bound(
    report: Callable[..., None],
) -> None:
    # Either outcome is safe; the bound is what the parser engine relies on.
    started = time.perf_counter()
    try:
        outcome = "match" if NESTED.search(NESTED_SUBJECT, timeout=TIMEOUT) else "none"
    except TimeoutError:
        outcome = "timeout"
    seconds = time.perf_counter() - started
    assert outcome in {"none", "timeout"}
    assert seconds < BOUND
    report("regex-nested", outcome=outcome, elapsed_ms=f"{seconds * 1000:.1f}")
