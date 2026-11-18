"""SPDX allow-list licence audit (merge gate check 6).

Python mode (default) reads the metadata of every installed distribution on the
given paths (default: the running interpreter, transitive packages included).
npm mode (--npm) reads every package of a package-lock.json (lockfile v2 or v3);
a package that only development dependencies pull in has scope "dev".

A licence passes when its SPDX expression is satisfied by the allow-list: OR
needs one allowed side, AND needs both. Everything else fails, including LGPL,
GPL, AGPL, SSPL, unknown licences and packages without licence metadata.

licence-exceptions.toml holds the reviewed exceptions, one [[exception]] table
each with ecosystem, package, licence, scope, reason, reviewer and date, plus
an optional "declared" (the exact text the package declares, when that is not
the SPDX identifier). An exception admits one package with one declared licence
in its scope: "runtime" also covers development use, "dev" covers development
only. A copyleft licence (LGPL, GPL, AGPL, SSPL) can never be an exception.
"""

import argparse
import json
import re
import sys
import tomllib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXCEPTIONS = ROOT / "licence-exceptions.toml"

# docs/ci-cd.md, rnd-report-2 5.1.
ALLOWED = frozenset(
    {
        "MIT",
        "BSD-2-Clause",
        "BSD-3-Clause",
        "Apache-2.0",
        "ISC",
        "PSF-2.0",
        "Python-2.0",
        "CNRI-Python",
        "0BSD",
        "Unlicense",
        "CC0-1.0",
    }
)
CANONICAL = {name.lower(): name for name in ALLOWED}
COPYLEFT = re.compile(r"(?<![A-Za-z])(?:LGPL|AGPL|GPL|SSPL)", re.IGNORECASE)
SCOPES = ("runtime", "dev")
ECOSYSTEMS = ("python", "npm")
REQUIRED_FIELDS = (
    "ecosystem",
    "package",
    "licence",
    "scope",
    "reason",
    "reviewer",
    "date",
)

# Legacy values of the free-text License field of Python packages.
ALIASES = {
    "mit license": "MIT",
    "apache software license": "Apache-2.0",
    "apache license 2.0": "Apache-2.0",
    "apache license, version 2.0": "Apache-2.0",
    "apache 2.0": "Apache-2.0",
    "isc license": "ISC",
    "isc license (iscl)": "ISC",
    "python software foundation license": "PSF-2.0",
    "psfl": "PSF-2.0",
    "the unlicense (unlicense)": "Unlicense",
}

# Last segment of "License :: ..." trove classifiers. The generic "BSD License"
# does not say which clauses and stays unresolved on purpose.
CLASSIFIERS = {
    "MIT License": "MIT",
    "BSD License": "BSD-UNSPECIFIED",
    "Apache Software License": "Apache-2.0",
    "ISC License (ISCL)": "ISC",
    "Python Software Foundation License": "PSF-2.0",
    "The Unlicense (Unlicense)": "Unlicense",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Creative Commons CC0 1.0 Universal (CC0 1.0) Public Domain Dedication": "CC0-1.0",
    "GNU Lesser General Public License v2 (LGPLv2)": "LGPL-2.0-only",
    "GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.0-or-later",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "GNU Lesser General Public License v3 or later (LGPLv3+)": "LGPL-3.0-or-later",
    "GNU Library or Lesser General Public License (LGPL)": "LGPL-UNSPECIFIED",
    "GNU General Public License (GPL)": "GPL-UNSPECIFIED",
    "GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "GNU General Public License v2 or later (GPLv2+)": "GPL-2.0-or-later",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "GNU General Public License v3 or later (GPLv3+)": "GPL-3.0-or-later",
    "GNU Affero General Public License v3": "AGPL-3.0-only",
    "GNU Affero General Public License v3 or later (AGPLv3+)": "AGPL-3.0-or-later",
}

TOKEN = re.compile(r"\(|\)|[^\s()]+")
RESERVED = {"AND", "OR", "WITH"}


@dataclass(frozen=True)
class LicenceException:
    """One reviewed entry of licence-exceptions.toml."""

    ecosystem: str
    package: str
    licence: str
    scope: str
    declared: str
    reason: str
    reviewer: str
    date: str


@dataclass(frozen=True)
class Package:
    """One package with its declared licence and its scope."""

    name: str
    version: str
    declared: str
    source: str
    scope: str


@dataclass(frozen=True)
class Result:
    """Outcome of one audit. No findings means a pass."""

    checked: int
    findings: list[Package]
    excepted: list[tuple[Package, LicenceException]]


class _Evaluator:
    """Evaluates an SPDX expression: OR needs one allowed side, AND needs both."""

    def __init__(self, text: str) -> None:
        self.tokens = TOKEN.findall(text)
        self.position = 0

    def _peek(self) -> str | None:
        if self.position < len(self.tokens):
            return self.tokens[self.position]
        return None

    def _take(self) -> str:
        token = self._peek()
        if token is None:
            raise ValueError("unexpected end of expression")
        self.position += 1
        return token

    def _is_operator(self, word: str) -> bool:
        token = self._peek()
        return token is not None and token.upper() == word

    def evaluate(self) -> bool:
        result = self._or()
        if self._peek() is not None:
            raise ValueError(f"unexpected token {self._peek()!r}")
        return result

    def _or(self) -> bool:
        result = self._and()
        while self._is_operator("OR"):
            self._take()
            right = self._and()
            result = result or right
        return result

    def _and(self) -> bool:
        result = self._atom()
        while self._is_operator("AND"):
            self._take()
            right = self._atom()
            result = result and right
        return result

    def _atom(self) -> bool:
        token = self._take()
        if token == "(":
            result = self._or()
            if self._take() != ")":
                raise ValueError("expected a closing parenthesis")
            return result
        if token == ")" or token.upper() in RESERVED:
            raise ValueError(f"unexpected token {token!r}")
        if self._is_operator("WITH"):
            self._take()
            self._take()
        return token.lower() in CANONICAL


def is_allowed_expression(expression: str) -> bool:
    """True when the allow-list satisfies the SPDX expression.

    Raises ValueError when the expression cannot be parsed.
    """
    return _Evaluator(expression).evaluate()


def _parses(expression: str) -> bool:
    try:
        _Evaluator(expression).evaluate()
    except ValueError:
        return False
    return True


def normalise(name: str) -> str:
    """PEP 503 name normalisation; npm names are already lower case."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _same(first: str, second: str) -> bool:
    return " ".join(first.split()).lower() == " ".join(second.split()).lower()


def load_exceptions(path: Path) -> list[LicenceException]:
    """Read and validate licence-exceptions.toml (absent file: none)."""
    if not path.is_file():
        return []
    entries = tomllib.loads(path.read_text(encoding="utf-8")).get("exception", [])
    if not isinstance(entries, list):
        raise ValueError(f"{path}: expected [[exception]] tables")
    result: list[LicenceException] = []
    for number, entry in enumerate(entries, 1):
        where = f"{path}: exception {number}"
        missing = [
            key for key in REQUIRED_FIELDS if not str(entry.get(key, "")).strip()
        ]
        if missing:
            raise ValueError(f"{where}: missing {', '.join(missing)}")
        unknown = sorted(set(entry) - set(REQUIRED_FIELDS) - {"declared"})
        if unknown:
            raise ValueError(f"{where}: unknown field {', '.join(unknown)}")
        values = {key: str(value).strip() for key, value in entry.items()}
        if values["ecosystem"] not in ECOSYSTEMS:
            raise ValueError(f"{where}: ecosystem must be one of {ECOSYSTEMS}")
        if values["scope"] not in SCOPES:
            raise ValueError(f"{where}: scope must be one of {SCOPES}")
        declared = values.get("declared") or values["licence"]
        if COPYLEFT.search(values["licence"]) or COPYLEFT.search(declared):
            raise ValueError(f"{where}: a copyleft licence can never be an exception")
        result.append(
            LicenceException(
                ecosystem=values["ecosystem"],
                package=values["package"],
                licence=values["licence"],
                scope=values["scope"],
                declared=declared,
                reason=values["reason"],
                reviewer=values["reviewer"],
                date=values["date"],
            )
        )
    return result


def declared_licence(meta: Any) -> tuple[str, str]:
    """Return (SPDX expression, where it came from) for one Python package."""
    expression = (meta.get("License-Expression") or "").strip()
    if expression:
        return expression, "License-Expression"

    legacy = (meta.get("License") or "").strip()
    if legacy and "\n" not in legacy and len(legacy) <= 120 and legacy != "UNKNOWN":
        candidate = ALIASES.get(legacy.lower(), legacy)
        if _parses(candidate):
            return candidate, "License field"

    tails = [
        classifier.split(" :: ")[-1]
        for classifier in meta.get_all("Classifier") or []
        if classifier.startswith("License ::")
    ]
    tails = [tail for tail in tails if tail != "OSI Approved"]
    if tails:
        mapped = [CLASSIFIERS.get(tail, "UNRECOGNISED") for tail in tails]
        return " AND ".join(mapped), "classifier " + "; ".join(tails)
    return "UNKNOWN", "no licence metadata"


def python_packages(
    distributions: Iterable[metadata.Distribution], scope: str
) -> list[Package]:
    """One Package per installed distribution (first one wins on duplicates)."""
    seen: set[str] = set()
    packages: list[Package] = []
    for distribution in distributions:
        meta = distribution.metadata
        name = meta.get("Name")
        if not name or normalise(name) in seen:
            continue
        seen.add(normalise(name))
        declared, source = declared_licence(meta)
        packages.append(Package(name, distribution.version, declared, source, scope))
    return sorted(packages, key=lambda package: normalise(package.name))


def _npm_licence(entry: Mapping[str, Any]) -> tuple[str, str]:
    value = entry.get("license")
    if isinstance(value, str) and value.strip():
        return value.strip(), "license"
    if isinstance(value, dict) and value.get("type"):
        return str(value["type"]), "license.type"
    legacy = entry.get("licenses")
    if isinstance(legacy, list) and legacy:
        kinds = [
            str(item.get("type") if isinstance(item, dict) else item) for item in legacy
        ]
        # The old "licenses" array offered a choice between its entries.
        return " OR ".join(kinds), "licenses"
    return "UNKNOWN", "no licence in package-lock.json"


def npm_packages(lock: Mapping[str, Any]) -> list[Package]:
    """One Package per name, version and scope in a v2 or v3 package-lock.json."""
    entries = lock.get("packages")
    if not isinstance(entries, dict):
        raise ValueError("package-lock.json has no 'packages' map (lockfile v2 or v3)")
    seen: set[tuple[str, str, str]] = set()
    packages: list[Package] = []
    for path, entry in sorted(entries.items()):
        if not path or not isinstance(entry, dict) or entry.get("link"):
            continue
        name = str(entry.get("name") or path.rsplit("node_modules/", 1)[-1])
        version = str(entry.get("version", "unknown"))
        scope = "dev" if entry.get("dev") or entry.get("devOptional") else "runtime"
        if (name, version, scope) in seen:
            continue
        seen.add((name, version, scope))
        declared, source = _npm_licence(entry)
        packages.append(Package(name, version, declared, source, scope))
    return packages


def find_exception(
    package: Package, ecosystem: str, exceptions: Sequence[LicenceException]
) -> LicenceException | None:
    """The exception that admits this package, declaration and scope, if any."""
    for entry in exceptions:
        if entry.ecosystem != ecosystem:
            continue
        if normalise(entry.package) != normalise(package.name):
            continue
        if package.scope == "runtime" and entry.scope != "runtime":
            continue
        if _same(entry.declared, package.declared):
            return entry
    return None


def audit(
    packages: Iterable[Package],
    ecosystem: str,
    exceptions: Sequence[LicenceException] = (),
) -> Result:
    """Check every package against the allow-list, then the exceptions."""
    checked = 0
    findings: list[Package] = []
    excepted: list[tuple[Package, LicenceException]] = []
    for package in packages:
        checked += 1
        try:
            allowed = is_allowed_expression(package.declared)
        except ValueError:
            allowed = False
        if allowed:
            continue
        entry = find_exception(package, ecosystem, exceptions)
        if entry is None or COPYLEFT.search(package.declared):
            findings.append(package)
        else:
            excepted.append((package, entry))
    return Result(checked, findings, excepted)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SPDX allow-list licence audit")
    parser.add_argument(
        "--npm",
        metavar="PACKAGE_LOCK",
        help="audit this package-lock.json instead of the Python packages",
    )
    parser.add_argument(
        "--path",
        action="append",
        help="directory holding *.dist-info metadata (repeatable; default: sys.path)",
    )
    parser.add_argument(
        "--scope",
        choices=SCOPES,
        default="runtime",
        help="scope of the Python packages (default: %(default)s)",
    )
    parser.add_argument(
        "--exceptions",
        default=str(DEFAULT_EXCEPTIONS),
        help="reviewed exceptions file (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    try:
        exceptions = load_exceptions(Path(args.exceptions))
        if args.npm:
            ecosystem, label = "npm", "npm"
            lock = json.loads(Path(args.npm).read_text(encoding="utf-8"))
            packages = npm_packages(lock)
        else:
            ecosystem, label = "python", f"python, {args.scope}"
            if args.path:
                distributions = metadata.distributions(path=args.path)
            else:
                distributions = metadata.distributions()
            packages = python_packages(distributions, args.scope)
    except (OSError, ValueError) as error:
        print(f"licence audit: {error}", file=sys.stderr)
        return 2
    if not packages:
        print("licence audit: no packages found", file=sys.stderr)
        return 2

    result = audit(packages, ecosystem, exceptions)
    print(f"licence audit ({label}): {result.checked} packages checked")
    for package, entry in result.excepted:
        print(
            f"EXCEPTION {package.name} {package.version} [{package.scope}]: "
            f"{entry.licence} ({entry.scope} exception, {entry.reviewer}, {entry.date})"
        )
    for package in result.findings:
        print(
            f"FAIL {package.name} {package.version} [{package.scope}]: "
            f"{package.declared} ({package.source})"
        )
    if result.findings:
        print(f"licence audit: {len(result.findings)} disallowed or unknown licence(s)")
        return 1
    print("licence audit: passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
