"""tools/npm_audit_gate.py: severity level, exceptions only for dev packages."""

import json
from pathlib import Path

import pytest

from tools import npm_audit_gate
from tools.npm_audit_gate import gate, load_exceptions

ROOT = Path(__file__).resolve().parent.parent
GHSA = "GHSA-fc5q-39xc-vjpf"
URL = f"https://github.com/advisories/{GHSA}"


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


def lock(dev: bool = True) -> dict:
    entry: dict[str, object] = {"version": "4.0.7", "license": "MIT"}
    if dev:
        entry["dev"] = True
    return {"lockfileVersion": 3, "packages": {"node_modules/picomatch": entry}}


def test_advisory_fails_without_an_exception() -> None:
    failing, excepted = gate(report(), lock(), {})
    assert [advisory.id for advisory in failing] == [GHSA]
    assert excepted == []


def test_exception_admits_a_development_only_package() -> None:
    failing, excepted = gate(report(), lock(dev=True), {GHSA: "reviewed"})
    assert failing == []
    assert [advisory.package for advisory in excepted] == ["picomatch"]


def test_exception_never_admits_a_shipped_package() -> None:
    failing, _ = gate(report(), lock(dev=False), {GHSA: "reviewed"})
    assert [advisory.id for advisory in failing] == [GHSA]


def test_exception_needs_the_package_in_the_lock_file() -> None:
    failing, _ = gate(report(node="node_modules/other"), lock(), {GHSA: "reviewed"})
    assert len(failing) == 1


def test_low_severity_is_below_the_gate() -> None:
    assert gate(report(severity="low"), lock(), {}) == ([], [])


def test_unknown_severity_counts_as_critical() -> None:
    failing, _ = gate(report(severity="new-level"), lock(), {})
    assert len(failing) == 1


def test_an_npm_error_report_is_refused() -> None:
    with pytest.raises(ValueError, match="not an npm audit report"):
        gate({"error": {"code": "ENOAUDIT"}}, lock(), {})


def test_invalid_exception_lines_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "exceptions"
    path.write_text(f"# comment\n{GHSA} reason\n", encoding="utf-8")
    assert load_exceptions(path) == {GHSA: "reason"}
    for line in (f"{GHSA}", "CVE-2026-1 reason", "GHSA-xxxx reason"):
        path.write_text(line + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="expected"):
            load_exceptions(path)


def test_repository_exceptions_file_is_valid() -> None:
    assert GHSA in load_exceptions(ROOT / ".npm-audit-exceptions")


def test_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    audit = tmp_path / "audit.json"
    package_lock = tmp_path / "package-lock.json"
    exceptions = tmp_path / "exceptions"
    audit.write_text(json.dumps(report()), encoding="utf-8")
    package_lock.write_text(json.dumps(lock()), encoding="utf-8")
    exceptions.write_text("", encoding="utf-8")
    arguments = [str(audit), str(package_lock), "--exceptions", str(exceptions)]
    assert npm_audit_gate.main(arguments) == 1
    assert f"FAIL {GHSA} picomatch (high)" in capsys.readouterr().out
    exceptions.write_text(f"{GHSA} reviewed\n", encoding="utf-8")
    assert npm_audit_gate.main(arguments) == 0
    assert npm_audit_gate.main([str(tmp_path / "absent.json"), str(package_lock)]) == 2
