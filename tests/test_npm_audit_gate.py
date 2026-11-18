"""tools/npm_audit_gate.py: severity level, exceptions only for dev packages."""

import json
from datetime import date
from pathlib import Path

import pytest

from tools import npm_audit_gate
from tools.npm_audit_gate import AuditException, gate, load_exceptions

ROOT = Path(__file__).resolve().parent.parent
GHSA = "GHSA-fc5q-39xc-vjpf"
URL = f"https://github.com/advisories/{GHSA}"
REVIEWED = AuditException(date(2026, 11, 18), "reviewed")


def report(severity: str = "high", node: str = "node_modules/picomatch") -> dict:
    return {
        "auditReportVersion": 2,
        "vulnerabilities": {
            "picomatch": {
                "severity": severity,
                "via": [
                    {"source": 1, "title": "ReDoS", "url": URL, "severity": severity}
                ],
                "nodes": [node],
            },
            "vite": {"severity": severity, "via": ["picomatch"], "nodes": []},
        },
    }


def lock(**flags: bool) -> dict:
    entry: dict[str, object] = {"version": "4.0.7", "license": "MIT", **flags}
    return {"lockfileVersion": 3, "packages": {"node_modules/picomatch": entry}}


def test_advisory_fails_without_an_exception() -> None:
    failing, excepted = gate(report(), lock(dev=True), {})
    assert [advisory.id for advisory in failing] == [GHSA]
    assert excepted == []


def test_exception_admits_a_development_only_package() -> None:
    failing, excepted = gate(report(), lock(dev=True), {GHSA: REVIEWED})
    assert failing == []
    assert [advisory.package for advisory in excepted] == ["picomatch"]


@pytest.mark.parametrize("flags", [{}, {"devOptional": True}, {"optional": True}])
def test_exception_never_admits_a_package_that_can_ship(flags: dict) -> None:
    failing, _ = gate(report(), lock(**flags), {GHSA: REVIEWED})
    assert [advisory.id for advisory in failing] == [GHSA]


def test_exception_needs_the_package_in_the_lock_file() -> None:
    nodes = report(node="node_modules/other")
    failing, _ = gate(nodes, lock(dev=True), {GHSA: REVIEWED})
    assert len(failing) == 1


def test_low_severity_is_below_the_gate() -> None:
    assert gate(report(severity="low"), lock(), {}) == ([], [])


def test_unknown_severity_counts_as_critical() -> None:
    failing, _ = gate(report(severity="new-level"), lock(), {})
    assert len(failing) == 1


def test_an_npm_error_report_is_refused() -> None:
    with pytest.raises(ValueError, match="not an npm audit report"):
        gate({"error": {"code": "ENOAUDIT"}}, lock(), {})


def test_exception_lines_need_id_date_and_reason(tmp_path: Path) -> None:
    path = tmp_path / "exceptions"
    path.write_text(f"# comment\n{GHSA} 2026-11-18 a reason\n", encoding="utf-8")
    today = date(2026, 11, 20)
    assert load_exceptions(path, today) == {
        GHSA: AuditException(date(2026, 11, 18), "a reason")
    }
    for line in (
        f"{GHSA} reason only",
        f"{GHSA} 2026-11-18",
        "CVE-2026-1 2026-11-18 reason",
        "GHSA-xxxx 2026-11-18 reason",
    ):
        path.write_text(line + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="expected"):
            load_exceptions(path, today)


def test_old_or_future_reviews_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "exceptions"
    path.write_text(f"{GHSA} 2026-11-18 reason\n", encoding="utf-8")
    assert load_exceptions(path, date(2027, 2, 16))  # 90 days later
    with pytest.raises(ValueError, match="review it again"):
        load_exceptions(path, date(2027, 2, 17))
    with pytest.raises(ValueError, match="in the future"):
        load_exceptions(path, date(2026, 11, 17))


def test_repository_exceptions_file_is_valid() -> None:
    exceptions = load_exceptions(ROOT / ".npm-audit-exceptions", date(2026, 11, 18))
    assert GHSA in exceptions


def test_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    audit = tmp_path / "audit.json"
    package_lock = tmp_path / "package-lock.json"
    exceptions = tmp_path / "exceptions"
    audit.write_text(json.dumps(report()), encoding="utf-8")
    package_lock.write_text(json.dumps(lock(dev=True)), encoding="utf-8")
    exceptions.write_text("", encoding="utf-8")
    arguments = [str(audit), str(package_lock), "--exceptions", str(exceptions)]
    assert npm_audit_gate.main(arguments) == 1
    assert f"FAIL {GHSA} picomatch (high)" in capsys.readouterr().out
    exceptions.write_text(f"{GHSA} {date.today()} reviewed\n", encoding="utf-8")
    assert npm_audit_gate.main(arguments) == 0
    assert npm_audit_gate.main([str(tmp_path / "absent.json"), str(package_lock)]) == 2
