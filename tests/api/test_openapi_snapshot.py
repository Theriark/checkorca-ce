"""docs/openapi.json stays equal to the app (the frontend's API types use it)."""

import json

import pytest

from tools.openapi_snapshot import SNAPSHOT, generate, render


def differences(stored: object, generated: object, path: str = "") -> list[str]:
    """The JSON paths where the two documents differ, for a readable failure."""
    if isinstance(stored, dict) and isinstance(generated, dict):
        found = []
        for key in sorted(set(stored) | set(generated)):
            if key not in stored:
                found.append(f"{path}/{key}: only in the app")
            elif key not in generated:
                found.append(f"{path}/{key}: only in docs/openapi.json")
            else:
                found += differences(stored[key], generated[key], f"{path}/{key}")
        return found
    if stored != generated:
        return [f"{path or '/'}: differs"]
    return []


def test_the_snapshot_equals_the_app() -> None:
    generated = generate()
    stored = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if stored != generated:
        report = "\n".join(differences(stored, generated)[:50])
        pytest.fail(
            "docs/openapi.json is stale; run python -m tools.openapi_snapshot\n"
            f"{report}\n"
            "OPENAPI-BEGIN\n"
            f"{json.dumps(generated, separators=(',', ':'))}\n"
            "OPENAPI-END",
            pytrace=False,
        )


def test_the_snapshot_is_written_in_its_canonical_form() -> None:
    text = SNAPSHOT.read_text(encoding="utf-8")
    assert text == render(json.loads(text))


def test_the_document_describes_the_c1_routes() -> None:
    paths = generate()["paths"]
    for path in (
        "/api/v1/auth/setup-state",
        "/api/v1/auth/first-run",
        "/api/v1/auth/login",
        "/api/v1/auth/logout",
        "/api/v1/auth/me",
        "/api/v1/users",
        "/api/v1/users/{user_id}",
        "/api/v1/tokens",
        "/api/v1/tokens/{token_id}",
    ):
        assert path in paths


def test_the_document_describes_the_c3_routes() -> None:
    paths = generate()["paths"]
    for path in (
        "/api/v1/clients",
        "/api/v1/clients/{client_id}",
        "/api/v1/clients/{client_id}/archive",
        "/api/v1/jobs",
        "/api/v1/jobs/{job_id}",
        "/api/v1/jobs/{job_id}/pause",
        "/api/v1/jobs/{job_id}/resume",
        "/api/v1/jobs/{job_id}/archive",
        "/api/v1/jobs/export.csv",
        "/api/v1/jobs/import.csv",
        "/api/v1/schedule/preview",
    ):
        assert path in paths
    export = paths["/api/v1/jobs/export.csv"]["get"]["responses"]["200"]
    assert list(export["content"]) == ["text/csv"]


def test_errors_are_declared_as_problem_documents() -> None:
    """The 4XX answers carry the media type the handlers send."""
    for path, operations in generate()["paths"].items():
        for method, operation in operations.items():
            problems = operation["responses"].get("4XX")
            if path.startswith("/api/v1/"):
                assert problems is not None, (method, path)
            if problems is not None:
                assert list(problems["content"]) == ["application/problem+json"]
