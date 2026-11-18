"""tools/third_party_notices.py: Python and npm licence texts, Debian statement."""

import json
from pathlib import Path

from tools import third_party_notices


def fake_site_packages(root: Path) -> Path:
    info = root / "sample-1.0.dist-info"
    (info / "licenses").mkdir(parents=True)
    (info / "METADATA").write_text(
        "Metadata-Version: 2.4\nName: sample\nVersion: 1.0\nLicense-Expression: MIT\n",
        encoding="utf-8",
    )
    (info / "licenses" / "LICENSE").write_text("Sample MIT text", encoding="utf-8")
    (info / "RECORD").write_text(
        "sample-1.0.dist-info/METADATA,,\n"
        "sample-1.0.dist-info/licenses/LICENSE,,\n"
        "sample-1.0.dist-info/RECORD,,\n",
        encoding="utf-8",
    )
    return root


def fake_frontend(root: Path) -> Path:
    lock = {
        "lockfileVersion": 3,
        "packages": {
            "": {"name": "frontend"},
            "node_modules/react": {"version": "19.0.0", "license": "MIT"},
            "node_modules/vite": {"version": "8.0.0", "license": "MIT", "dev": True},
        },
    }
    (root / "node_modules" / "react").mkdir(parents=True)
    (root / "node_modules" / "react" / "LICENSE").write_text("React MIT text")
    (root / "package-lock.json").write_text(json.dumps(lock), encoding="utf-8")
    return root


def test_notices_hold_shipped_licence_texts_only(tmp_path: Path) -> None:
    site = fake_site_packages(tmp_path / "site")
    frontend = fake_frontend(tmp_path / "frontend")
    text = third_party_notices.build(site, frontend)
    assert "sample 1.0\nLicence: MIT" in text
    assert "Sample MIT text" in text
    assert "react 19.0.0" in text
    assert "React MIT text" in text
    # Development packages are not in the image.
    assert "vite 8.0.0" not in text
    assert "/usr/share/doc/<package>/copyright" in text


def test_main_writes_the_file_and_refuses_an_empty_environment(
    tmp_path: Path,
) -> None:
    site = fake_site_packages(tmp_path / "site")
    frontend = fake_frontend(tmp_path / "frontend")
    output = tmp_path / "THIRD_PARTY_NOTICES"
    arguments = ["--frontend", str(frontend), "--output", str(output)]
    assert third_party_notices.main(["--site-packages", str(site), *arguments]) == 0
    assert "PART 3: DEBIAN" in output.read_text(encoding="utf-8")
    (tmp_path / "empty").mkdir()
    empty = ["--site-packages", str(tmp_path / "empty"), *arguments]
    assert third_party_notices.main(empty) == 1
