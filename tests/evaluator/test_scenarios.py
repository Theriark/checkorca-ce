"""The golden scenarios of tests/evaluator/scenarios (phase-plan-2 C7 list).

Each scenario runs on the injected FakeClock through evaluator_runner.py,
which also checks after every step that evaluating again changes nothing and
that job state ok means the newest closed occurrence is verified.
"""

from collections import Counter
from typing import Any

import pytest

import evaluator_runner as runner

SCENARIOS = runner.load()


def test_there_are_at_least_40_scenarios_with_unique_names() -> None:
    assert len(SCENARIOS) >= 40
    names = Counter(scenario["name"] for scenario in SCENARIOS)
    assert [name for name, count in names.items() if count > 1] == []


def test_the_phase_plan_list_is_covered() -> None:
    """Every item of the phase-plan-2 C7 test list has a scenario."""
    text = " ".join(scenario["name"].lower() for scenario in SCENARIOS)
    for words in (
        "nightly success",
        "successful retry",
        "success then failure",
        "start without a finish",
        "pending until its deadline",
        "missed after the escalation",
        "three hours late",
        "two successes",
        "created mid-day",
        "paused",
        "lisbon",
        "new york",
        "threshold of 3",
        "warning_counts_ok",
        "warning needs attention",
        "unknown result never verifies",
        "maintenance",
        "late success after missed",
    ):
        assert words in text, words


@pytest.mark.parametrize(
    "scenario",
    SCENARIOS,
    ids=[f"{item['file']}:{item['name']}" for item in SCENARIOS],
)
def test_scenario(scenario: dict[str, Any]) -> None:
    for step, run, evaluation in runner.steps(scenario):
        runner.check_step(step, run, evaluation)
