"""Write docs/openapi.json, the OpenAPI document of the /api/v1 routes.

The frontend generates its API types from this file (phase C2-F), and
tests/api/test_openapi_snapshot.py fails while it differs from the app. Run it
after changing a route or a schema:

  python -m tools.openapi_snapshot
"""

import base64
import json
import sys
from pathlib import Path
from typing import Any

from app.main import create_app
from app.settings import load_settings

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "docs" / "openapi.json"

# The document does not depend on these values; they only let the app be built.
PLACEHOLDER_SETTINGS = {
    "secret_key": "openapi-snapshot-placeholder-0000000000",
    "fernet_key": base64.urlsafe_b64encode(bytes(32)).decode(),
    "database_url": "postgresql+asyncpg://unused@127.0.0.1:1/unused",
}


def generate() -> dict[str, Any]:
    """The OpenAPI document of the app, as plain JSON values."""
    app = create_app(load_settings(**PLACEHOLDER_SETTINGS), static_dir=None)
    document: dict[str, Any] = json.loads(json.dumps(app.openapi()))
    return document


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    SNAPSHOT.write_text(render(generate()), encoding="utf-8")
    print(f"wrote {SNAPSHOT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
