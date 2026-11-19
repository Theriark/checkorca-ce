"""tools/licence_audit.py: allow-list, exceptions and their scope."""

import json
from importlib import metadata
from pathlib import Path

import pytest

from tools import licence_audit
from tools.licence_audit import LicenceException, Package, audit, load_exceptions

ROOT = Path(__file__).resolve().parent.parent


def fake_distribution(root: Path, name: str, *headers: str) -> Path:
    """A minimal installed distribution with the given metadata headers."""
    info = root / f"{name}-1.0.dist-info"
    info.mkdir(parents=True)
    lines = ["Metadata-Version: 2.4", f"Name: {name}", "Version: 1.0", *headers]
    (info / "METADATA").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return root


def python_package(root: Path, name: str, *headers: str) -> Package:
    fake_distribution(root, name, *headers)
    distributions = metadata.distributions(path=[str(root)])
    [package] = licence_audit.python_packages(distributions, "runtime")
    return package


def exception(**fields: str) -> LicenceException:
    values = {
        "ecosystem": "python",
        "package": "sample",
        "licence": "MPL-2.0",
        "scope": "runtime",
        "declared": "MPL-2.0",
        "reason": "synthetic test entry",
        "reviewer": "test",
        "date": "2026-11-18",
    }
    values.update(fields)
    return LicenceException(**values)


@pytest.mark.parametrize(
    "headers",
    [
        ["License-Expression: MIT"],
        ["License-Expression: Apache-2.0 OR GPL-2.0-only"],
        ["License-Expression: (MIT AND BSD-3-Clause)"],
        ["License: MIT License"],
        ["License: PSFL"],
        ["Classifier: License :: OSI Approved :: MIT License"],
    ],
)
def test_allowed_licences_pass(tmp_path: Path, headers: list[str]) -> None:
    package = python_package(tmp_path, "sample", *headers)
    assert audit([package], "python").findings == []


def test_fake_lgpl_package_fails(tmp_path: Path) -> None:
    package = python_package(tmp_path, "sample", "License-Expression: LGPL-3.0-only")
    assert audit([package], "python").findings == [package]


def test_lgpl_fails_even_with_an_exception(tmp_path: Path) -> None:
    package = python_package(tmp_path, "sample", "License: LGPL-3.0-only")
    entry = exception(licence="LGPL-3.0-only", declared="LGPL-3.0-only")
    assert audit([package], "python", [entry]).findings == [package]


def test_unknown_licence_fails(tmp_path: Path) -> None:
    package = python_package(tmp_path, "sample", "License: Proprietary")
    assert audit([package], "python").findings == [package]


def test_missing_licence_metadata_fails(tmp_path: Path) -> None:
    package = python_package(tmp_path, "sample")
    assert package.declared == "UNKNOWN"
    assert audit([package], "python").findings == [package]


def test_and_with_a_disallowed_side_fails(tmp_path: Path) -> None:
    package = python_package(tmp_path, "sample", "License-Expression: MIT AND MPL-2.0")
    assert audit([package], "python").findings == [package]


def test_generic_bsd_classifier_needs_a_reviewed_declaration(tmp_path: Path) -> None:
    classifier = "Classifier: License :: OSI Approved :: BSD License"
    package = python_package(tmp_path, "sample", classifier)
    assert package.declared == "BSD-UNSPECIFIED"
    assert audit([package], "python").findings == [package]
    entry = exception(licence="BSD-3-Clause", declared="BSD-UNSPECIFIED")
    assert audit([package], "python", [entry]).findings == []


def test_runtime_package_needs_a_runtime_exception(tmp_path: Path) -> None:
    package = python_package(tmp_path, "sample", "License: MPL-2.0")
    assert audit([package], "python", [exception(scope="dev")]).findings == [package]
    result = audit([package], "python", [exception(scope="runtime")])
    assert result.findings == []
    assert [entry.scope for _, entry in result.excepted] == ["runtime"]


def test_dev_package_accepts_a_dev_or_runtime_exception() -> None:
    package = Package("sample", "1.0", "MPL-2.0", "test", "dev")
    for scope in ("dev", "runtime"):
        assert audit([package], "python", [exception(scope=scope)]).findings == []


def test_exception_matches_ecosystem_name_and_declaration() -> None:
    package = Package("Sample_Pkg", "1.0", "MPL-2.0", "test", "runtime")
    assert audit([package], "python", [exception(package="sample-pkg")]).findings == []
    for entry in (
        exception(package="sample-pkg", ecosystem="npm"),
        exception(package="other"),
        exception(package="sample-pkg", declared="CC-BY-4.0"),
    ):
        assert audit([package], "python", [entry]).findings == [package]


def npm_lock(**packages: dict[str, object]) -> dict[str, object]:
    entries: dict[str, object] = {"": {"name": "frontend", "version": "27.0.0"}}
    entries.update({f"node_modules/{name}": entry for name, entry in packages.items()})
    return {"lockfileVersion": 3, "packages": entries}


def test_npm_scopes_and_licences() -> None:
    lock = npm_lock(
        react={"version": "19.0.0", "license": "MIT"},
        typefest={"version": "1.0.0", "license": "(MIT OR CC0-1.0)", "dev": True},
        old={"version": "1.0.0", "licenses": [{"type": "MIT"}, {"type": "GPL-2.0"}]},
        bare={"version": "1.0.0"},
        devopt={"version": "1.0.0", "license": "ISC", "devOptional": True},
    )
    packages = {package.name: package for package in licence_audit.npm_packages(lock)}
    assert packages["react"].scope == "runtime"
    assert packages["typefest"].scope == "dev"
    # devOptional can ship in the production tree.
    assert packages["devopt"].scope == "runtime"
    assert packages["old"].declared == "MIT OR GPL-2.0"
    assert packages["bare"].declared == "UNKNOWN"
    result = audit(packages.values(), "npm")
    assert [package.name for package in result.findings] == ["bare"]


def test_npm_cc_by_package_passes_only_as_dev() -> None:
    entry = exception(
        ecosystem="npm",
        package="caniuse-lite",
        licence="CC-BY-4.0",
        declared="CC-BY-4.0",
        scope="dev",
    )
    for scope, failing in (("dev", 0), ("runtime", 1)):
        package = Package("caniuse-lite", "1.0", "CC-BY-4.0", "license", scope)
        assert len(audit([package], "npm", [entry]).findings) == failing


def test_npm_lock_without_packages_is_refused() -> None:
    with pytest.raises(ValueError, match="lockfile v2 or v3"):
        licence_audit.npm_packages({"lockfileVersion": 1})


ENTRY = """
[[exception]]
ecosystem = "python"
package = "sample"
licence = "MPL-2.0"
scope = "runtime"
reason = "synthetic"
reviewer = "test"
date = 2026-11-18
"""


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (('scope = "runtime"', 'scope = "always"'), "scope"),
        (('ecosystem = "python"', 'ecosystem = "cargo"'), "ecosystem"),
        (('reason = "synthetic"', ""), "missing reason"),
        (('reviewer = "test"', 'reviewer = "test"\nnote = "x"'), "unknown field"),
        (('licence = "MPL-2.0"', 'licence = "GPL-3.0-only"'), "copyleft"),
        (('licence = "MPL-2.0"', 'licence = "MPL-2.0"\ndeclared = "AGPL-3.0"'), "copy"),
    ],
)
def test_invalid_exceptions_are_refused(
    tmp_path: Path, change: tuple[str, str], message: str
) -> None:
    path = tmp_path / "exceptions.toml"
    path.write_text(ENTRY.replace(*change), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_exceptions(path)


def test_absent_exceptions_file_means_none(tmp_path: Path) -> None:
    assert load_exceptions(tmp_path / "absent.toml") == []


def test_repository_exceptions_are_the_reviewed_set() -> None:
    entries = load_exceptions(ROOT / "licence-exceptions.toml")
    found = {
        (entry.ecosystem, entry.package, entry.licence, entry.scope)
        for entry in entries
    }
    for expected in (
        ("python", "certifi", "MPL-2.0", "runtime"),
        ("python", "hypothesis", "MPL-2.0", "dev"),
        ("npm", "axe-core", "MPL-2.0", "dev"),
        ("npm", "lightningcss", "MPL-2.0", "dev"),
        ("npm", "caniuse-lite", "CC-BY-4.0", "dev"),
        ("npm", "@fontsource-variable/inter", "OFL-1.1", "runtime"),
        ("npm", "@fontsource-variable/jetbrains-mono", "OFL-1.1", "runtime"),
    ):
        assert expected in found
    # Only certifi, cffi and the two OFL font packages (legal R-5, phase C2)
    # may be shipped under an exception.
    runtime = sorted(entry.package for entry in entries if entry.scope == "runtime")
    assert runtime == [
        "@fontsource-variable/inter",
        "@fontsource-variable/jetbrains-mono",
        "certifi",
        "cffi",
    ]


def test_main_python_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = fake_distribution(tmp_path / "good", "fine", "License-Expression: MIT")
    bad = fake_distribution(tmp_path / "bad", "lgpl", "License-Expression: LGPL-2.1")
    none = tmp_path / "empty.toml"
    assert licence_audit.main(["--path", str(good), "--exceptions", str(none)]) == 0
    assert licence_audit.main(["--path", str(bad), "--exceptions", str(none)]) == 1
    assert "FAIL lgpl 1.0 [runtime]: LGPL-2.1" in capsys.readouterr().out
    (tmp_path / "nothing").mkdir()
    assert licence_audit.main(["--path", str(tmp_path / "nothing")]) == 2


def test_main_npm_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lock = tmp_path / "package-lock.json"
    lock.write_text(json.dumps(npm_lock(react={"version": "1", "license": "MIT"})))
    assert licence_audit.main(["--npm", str(lock)]) == 0
    assert "licence audit: passed" in capsys.readouterr().out
    assert licence_audit.main(["--npm", str(tmp_path / "absent.json")]) == 2
