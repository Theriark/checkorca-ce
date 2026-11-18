"""Write THIRD_PARTY_NOTICES for the container image (legal R-3, R-4).

Run by the Dockerfile in the build stage. The file lists, with their licence
texts, every Python distribution installed in the image's virtual environment
and every npm package shipped in the built web app (the non-development
packages of package-lock.json), then states how the Debian packages of the base
image are licensed. The image puts it next to LICENSE and NOTICE.

Usage:
  python tools/third_party_notices.py --site-packages DIR --frontend DIR \
      --output THIRD_PARTY_NOTICES
"""

import argparse
import json
import subprocess
import sys
from collections.abc import Iterable, Sequence
from importlib import metadata
from pathlib import Path

LICENCE_PREFIXES = ("license", "licence", "copying", "notice", "authors")
RULE = "=" * 78

DEBIAN_STATEMENT = """\
The image is built on the official python:3.12-slim image (Debian), pinned by
digest in the Dockerfile. Its operating-system packages are unmodified Debian
packages. Each keeps its own licence, some of them GPL or LGPL; the terms of a
package are in /usr/share/doc/<package>/copyright inside the image, and its
source is available from Debian (https://sources.debian.org and
https://snapshot.debian.org). Checkorca-CE does not modify or link these
packages into its own code. The SBOM of each image digest (sbom.spdx.json,
a CI artefact) lists them with their versions."""


def _is_licence_file(name: str) -> bool:
    return name.lower().startswith(LICENCE_PREFIXES)


def python_section(distributions: Iterable[metadata.Distribution]) -> list[str]:
    """Name, version, declared licence and licence texts of each distribution."""
    lines: list[str] = []
    seen: set[str] = set()
    ordered = sorted(distributions, key=lambda item: item.metadata["Name"] or "")
    for distribution in ordered:
        name = distribution.metadata["Name"]
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        meta = distribution.metadata
        declared = meta.get("License-Expression") or meta.get("License") or ""
        if "\n" in declared or len(declared) > 120:
            declared = "see the licence text below"
        lines += [RULE, f"{name} {distribution.version}"]
        lines.append(f"Licence: {declared or 'see the licence text below'}")
        texts = 0
        for item in distribution.files or []:
            parts = item.parts
            if not parts or not parts[0].endswith(".dist-info"):
                continue
            if "licenses" not in parts[1:] and not _is_licence_file(parts[-1]):
                continue
            path = Path(str(distribution.locate_file(item)))
            if not path.is_file():
                continue
            texts += 1
            lines += ["", f"--- {'/'.join(parts[1:])}", ""]
            lines.append(path.read_text(encoding="utf-8", errors="replace").rstrip())
        if not texts:
            lines.append("(The package ships no licence file in its metadata.)")
        lines.append("")
    return lines


def npm_section(frontend: Path) -> list[str]:
    """The packages shipped in the built web app and their licence texts."""
    lock = json.loads((frontend / "package-lock.json").read_text(encoding="utf-8"))
    lines: list[str] = []
    for path, entry in sorted(lock.get("packages", {}).items()):
        if not path or entry.get("dev") or entry.get("devOptional"):
            continue
        name = entry.get("name") or path.rsplit("node_modules/", 1)[-1]
        lines += [RULE, f"{name} {entry.get('version', 'unknown')}"]
        lines.append(f"Licence: {entry.get('license', 'unknown')}")
        folder = frontend / path
        found = folder.iterdir() if folder.is_dir() else []
        files = sorted(p for p in found if p.is_file() and _is_licence_file(p.name))
        for item in files:
            lines += ["", f"--- {item.name}", ""]
            lines.append(item.read_text(encoding="utf-8", errors="replace").rstrip())
        if not files:
            lines.append("(The package ships no licence file.)")
        lines.append("")
    return lines


def debian_section() -> list[str]:
    """The statement on the Debian packages and the installed package list."""
    lines = [DEBIAN_STATEMENT, ""]
    try:
        listing = subprocess.run(
            ["dpkg-query", "-W", "-f=${Package} ${Version}\n"],
            capture_output=True,
            check=True,
            text=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        lines.append("(dpkg-query was not available when this file was written.)")
        return lines
    lines.append("Debian packages in the base image:")
    lines += [f"  {line}" for line in sorted(listing.splitlines()) if line.strip()]
    return lines


def build(site_packages: Path, frontend: Path) -> str:
    distributions = list(metadata.distributions(path=[str(site_packages)]))
    if not distributions:
        raise ValueError(f"no Python distributions found in {site_packages}")
    lines = [
        "THIRD-PARTY NOTICES FOR THE CHECKORCA-CE CONTAINER IMAGE",
        "",
        "Checkorca-CE itself is licensed under the MIT License (see LICENSE and",
        "NOTICE). The image also contains the third-party software below, each",
        "part under its own licence.",
        "",
        RULE,
        "PART 1: PYTHON PACKAGES",
        "",
    ]
    lines += python_section(distributions)
    lines += [RULE, "PART 2: NPM PACKAGES IN THE BUILT WEB APP", ""]
    lines += npm_section(frontend)
    lines += [RULE, "PART 3: DEBIAN OPERATING-SYSTEM PACKAGES", ""]
    lines += debian_section()
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write THIRD_PARTY_NOTICES")
    parser.add_argument("--site-packages", required=True, type=Path)
    parser.add_argument("--frontend", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        text = build(args.site_packages, args.frontend)
    except (OSError, ValueError) as error:
        print(f"third party notices: {error}", file=sys.stderr)
        return 1
    args.output.write_text(text, encoding="utf-8")
    print(f"third party notices: wrote {args.output} ({len(text)} characters)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
