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


def test_the_document_describes_the_c4_routes() -> None:
    paths = generate()["paths"]
    for path in (
        "/api/v1/inboxes",
        "/api/v1/inboxes/{inbox_id}",
        "/api/v1/inboxes/{inbox_id}/token",
        "/api/v1/messages",
        "/api/v1/messages/{message_id}",
        "/api/v1/results",
        "/api/v1/jobs/{job_id}/results",
        "/api/v1/system/status",
    ):
        assert path in paths
    # Write-only (D-6): no inbox answer has a password or the token's hash.
    schemas = generate()["components"]["schemas"]
    hidden = {"password", "imap_password_enc", "token_sha256"}
    for name in ("InboxOut", "InboxCreated", "ImapOut", "InboxActivity"):
        assert not hidden & set(schemas[name]["properties"])


def test_the_document_describes_the_c4_receivers() -> None:
    paths = generate()["paths"]
    ingest = paths["/api/v1/ingest/email/{inbox_code}"]["post"]
    assert list(ingest["requestBody"]["content"]) == ["message/rfc822"]
    assert "post" in paths["/api/v1/results"]
    assert "post" in paths["/api/v1/messages/upload"]
    for path in ("/api/v1/ping/{ping_token}", "/api/v1/ping/{ping_token}/{signal}"):
        assert set(paths[path]) == {"get", "post"}
        answer = paths[path]["get"]["responses"]["200"]
        assert list(answer["content"]) == ["text/plain"]


def test_the_document_describes_the_c5_routes() -> None:
    paths = generate()["paths"]
    for path, method in (
        ("/api/v1/packs", "get"),
        ("/api/v1/packs/{pack_id}", "get"),
        ("/api/v1/packs/{pack_id}", "put"),
        ("/api/v1/packs/import", "post"),
        ("/api/v1/packs/{pack_id}/export", "get"),
        ("/api/v1/packs/{pack_id}/enable", "post"),
        ("/api/v1/packs/{pack_id}/disable", "post"),
        ("/api/v1/packs/test", "post"),
        ("/api/v1/unmatched", "get"),
        ("/api/v1/unmatched/{result_id}/assign", "post"),
        ("/api/v1/unmatched/{result_id}/create-job", "post"),
        ("/api/v1/unmatched/{result_id}/suggest-schedule", "get"),
    ):
        assert method in paths[path], (method, path)
    # packs/test reads its body itself; the document still declares it.
    body = paths["/api/v1/packs/test"]["post"]["requestBody"]["content"]
    assert set(body["application/json"]["schema"]["properties"]) == {"raw", "pack"}
    export = paths["/api/v1/packs/{pack_id}/export"]["get"]["responses"]["200"]
    assert list(export["content"]) == ["application/yaml"]
    problem = generate()["components"]["schemas"]["Problem"]["properties"]
    assert "issues" in problem


def test_the_document_describes_the_c7_routes() -> None:
    """Occurrence and Flip fields exactly as in the Interfaces chapter."""
    document = generate()
    paths = document["paths"]
    occurrences = paths["/api/v1/jobs/{job_id}/occurrences"]["get"]
    names = {parameter["name"] for parameter in occurrences["parameters"]}
    assert {"job_id", "from", "to", "cursor", "limit"} <= names
    flips = paths["/api/v1/flips"]["get"]
    names = {parameter["name"] for parameter in flips["parameters"]}
    assert {"job_id", "client_id", "since", "cursor", "limit"} <= names
    schemas = document["components"]["schemas"]
    assert set(schemas["OccurrenceOut"]["properties"]) == {
        "job_id",
        "scheduled_for",
        "deadline",
        "state",
        "result_id",
        "note",
    }
    assert set(schemas["FlipOut"]["properties"]) == {
        "id",
        "job_id",
        "client_id",
        "from_state",
        "to_state",
        "reason",
        "at",
    }
    states = schemas["OccurrenceOut"]["properties"]["state"]["enum"]
    assert states == [
        "pending",
        "running",
        "verified",
        "warning",
        "failed",
        "overdue",
        "missed",
        "maintenance",
    ]


def test_the_document_describes_the_c9_routes() -> None:
    """Channels, rules, notifications and the digest settings; the channel
    secret is write-only (D-6) and jobs say who acknowledged."""
    document = generate()
    paths = document["paths"]
    for path, method in (
        ("/api/v1/channels", "get"),
        ("/api/v1/channels", "post"),
        ("/api/v1/channels/{channel_id}", "get"),
        ("/api/v1/channels/{channel_id}", "patch"),
        ("/api/v1/channels/{channel_id}", "delete"),
        ("/api/v1/channels/{channel_id}/test", "post"),
        ("/api/v1/channels/check-url", "post"),
        ("/api/v1/channel-rules", "get"),
        ("/api/v1/channel-rules", "post"),
        ("/api/v1/channel-rules/{rule_id}", "patch"),
        ("/api/v1/channel-rules/{rule_id}", "delete"),
        ("/api/v1/notifications", "get"),
        ("/api/v1/settings", "get"),
        ("/api/v1/settings", "patch"),
    ):
        assert method in paths[path], (method, path)
    schemas = document["components"]["schemas"]
    hidden = {"secret", "secret_enc", "password"}
    for name in ("ChannelOut", "ChannelPage", "ChannelTestResult"):
        assert not hidden & set(schemas[name]["properties"])
    assert "secret" in schemas["NewChannel"]["properties"]
    channel = set(schemas["ChannelOut"]["properties"])
    assert {"secret_set", "secret_hint", "last_status"} <= channel
    notification = schemas["NotificationOut"]["properties"]
    expected = {"flip_id", "channel_id", "status", "attempts", "error", "sent_at"}
    assert expected <= set(notification)
    assert notification["status"]["enum"] == ["queued", "sent", "retrying", "failed"]
    assert set(schemas["DigestSettingsOut"]["properties"]) == {
        "digest_time_local",
        "digest_timezone",
        "reminder_24h",
    }
    assert "acknowledged_by" in schemas["JobOut"]["properties"]
    assert set(schemas["AcknowledgedBy"]["properties"]) == {"id", "email"}


def test_errors_are_declared_as_problem_documents() -> None:
    """The 4XX answers carry the media type the handlers send."""
    for path, operations in generate()["paths"].items():
        for method, operation in operations.items():
            problems = operation["responses"].get("4XX")
            if path.startswith("/api/v1/"):
                assert problems is not None, (method, path)
            if problems is not None:
                assert list(problems["content"]) == ["application/problem+json"]
