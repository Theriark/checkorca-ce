"""The matcher: results to jobs, and schedules suggested from results (C5).

Pure code; the repositories load what it compares.
"""

from app.matcher.match import (
    Bound,
    ClientRef,
    JobRef,
    Matcher,
    NoMatch,
    NoMatchReason,
    names_client,
    same_names,
    tokens,
)
from app.matcher.suggest import (
    MIN_RESULTS,
    Basis,
    RunTimes,
    Suggestion,
    TooFewResults,
    circular_median,
    suggest_daily,
)

__all__ = [
    "MIN_RESULTS",
    "Basis",
    "Bound",
    "ClientRef",
    "JobRef",
    "Matcher",
    "NoMatch",
    "NoMatchReason",
    "RunTimes",
    "Suggestion",
    "TooFewResults",
    "circular_median",
    "names_client",
    "same_names",
    "suggest_daily",
    "tokens",
]
