"""npm audit gate with reviewed exceptions (merge gate check 5).

Reads the JSON report of npm audit (npm 7 or later) and package-lock.json and
fails on every advisory of moderate severity or higher, except those listed in
.npm-audit-exceptions (one line each: the GHSA id, the review date YYYY-MM-DD,
then the reason). An exception only applies while every vulnerable copy of the
package is a development package ("dev": true in package-lock.json;
"devOptional" can be in the production tree, so it does not count): an
advisory that reaches the built web app always fails. An exception reviewed
more than 90 days ago fails until it is reviewed again, so a fixed release is
not missed.

Usage (in frontend/):
  npm audit --json > audit.json || true
  python3 ../tools/npm_audit_gate.py audit.json package-lock.json
"""

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXCEPTIONS = ROOT / ".npm-audit-exceptions"
LEVELS = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
ADVISORY = re.compile(r"GHSA(?:-[23456789cfghjmpqrvwx]{4}){3}")
MAX_AGE_DAYS = 90


@dataclass(frozen=True)
class AuditException:
    """One reviewed line of .npm-audit-exceptions."""

    reviewed: date
    reason: str


@dataclass(frozen=True)
class Advisory:
    """One advisory of the report, on one vulnerable package."""

    id: str
    package: str
    severity: str
    title: str
    nodes: tuple[str, ...]


def load_exceptions(
    path: Path, today: date | None = None, max_age_days: int = MAX_AGE_DAYS
) -> dict[str, AuditException]:
    """Read .npm-audit-exceptions: advisory id, review date and reason per line."""
    if not path.is_file():
        return {}
    current = today or date.today()
    exceptions: dict[str, AuditException] = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        where = f"{path}:{number}"
        parts = text.split(maxsplit=2)
        try:
            advisory, reviewed_text, reason = parts
            reviewed = date.fromisoformat(reviewed_text)
        except ValueError:
            raise ValueError(f"{where}: expected 'GHSA-id YYYY-MM-DD reason'") from None
        if not ADVISORY.fullmatch(advisory):
            raise ValueError(f"{where}: expected 'GHSA-id YYYY-MM-DD reason'")
        if reviewed > current:
            raise ValueError(f"{where}: {advisory} has a review date in the future")
        if (current - reviewed).days > max_age_days:
            raise ValueError(
                f"{where}: {advisory} was reviewed on {reviewed}; review it again"
                f" (at most {max_age_days} days)"
            )
        exceptions[advisory] = AuditException(reviewed, reason)
    return exceptions


def advisories(report: Mapping[str, Any]) -> list[Advisory]:
    """Every advisory record of the report.

    Entries whose "via" is only a package name point at another vulnerable
    package of the report and add no advisory of their own.
    """
    if "error" in report or not isinstance(report.get("vulnerabilities"), dict):
        raise ValueError("not an npm audit report (npm 7 or later)")
    found: list[Advisory] = []
    for name, entry in sorted(report["vulnerabilities"].items()):
        for via in entry.get("via", []):
            if not isinstance(via, dict):
                continue
            match = ADVISORY.search(str(via.get("url", "")))
            found.append(
                Advisory(
                    id=match.group(0) if match else str(via.get("source", "unknown")),
                    package=name,
                    severity=str(via.get("severity", "unknown")),
                    title=str(via.get("title", "")),
                    nodes=tuple(entry.get("nodes", [])),
                )
            )
    return found


def is_development_only(nodes: Sequence[str], lock: Mapping[str, Any]) -> bool:
    """True when every listed copy is a development package of the lock file."""
    packages = lock.get("packages", {})
    if not nodes:
        return False
    for node in nodes:
        entry = packages.get(node)
        if not isinstance(entry, dict) or entry.get("dev") is not True:
            return False
    return True


def gate(
    report: Mapping[str, Any],
    lock: Mapping[str, Any],
    exceptions: Mapping[str, AuditException],
    level: str = "moderate",
) -> tuple[list[Advisory], list[Advisory]]:
    """Return (failing, excepted) advisories at or above the level."""
    failing: list[Advisory] = []
    excepted: list[Advisory] = []
    for advisory in advisories(report):
        # An unknown severity counts as critical.
        if LEVELS.get(advisory.severity, LEVELS["critical"]) < LEVELS[level]:
            continue
        if advisory.id in exceptions and is_development_only(advisory.nodes, lock):
            excepted.append(advisory)
        else:
            failing.append(advisory)
    return failing, excepted


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="npm audit gate")
    parser.add_argument("report", type=Path, help="output of npm audit --json")
    parser.add_argument("lock", type=Path, help="package-lock.json")
    parser.add_argument("--level", choices=sorted(LEVELS), default="moderate")
    parser.add_argument("--exceptions", type=Path, default=DEFAULT_EXCEPTIONS)
    args = parser.parse_args(argv)
    try:
        exceptions = load_exceptions(args.exceptions)
        report = json.loads(args.report.read_text(encoding="utf-8"))
        lock = json.loads(args.lock.read_text(encoding="utf-8"))
        failing, excepted = gate(report, lock, exceptions, args.level)
    except (OSError, ValueError) as error:
        print(f"npm audit gate: {error}", file=sys.stderr)
        return 2
    for advisory in excepted:
        print(
            f"EXCEPTION {advisory.id} {advisory.package} ({advisory.severity}, "
            f"development only, reviewed {exceptions[advisory.id].reviewed}): "
            f"{exceptions[advisory.id].reason}"
        )
    for advisory in failing:
        print(
            f"FAIL {advisory.id} {advisory.package} ({advisory.severity}): "
            f"{advisory.title}"
        )
    if failing:
        print(f"npm audit gate: {len(failing)} advisory(ies) at {args.level} or above")
        return 1
    print(f"npm audit gate: passed ({len(excepted)} reviewed exception(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
