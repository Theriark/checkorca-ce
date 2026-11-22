"""docs/openapi.json describes the phase C8-B routes with the fields of the
Interfaces chapter (Dashboard); additions are listed in docs/dashboard.md."""

from tools.openapi_snapshot import generate


def test_the_document_describes_the_c8_routes() -> None:
    document = generate()
    paths = document["paths"]
    for path, method in (
        ("/api/v1/dashboard/today", "get"),
        ("/api/v1/dashboard/ribbon", "get"),
        ("/api/v1/dashboard/trend", "get"),
        ("/api/v1/dashboard/breakdown", "get"),
        ("/api/v1/activity", "get"),
        ("/api/v1/jobs/{job_id}/acknowledge", "post"),
        ("/api/v1/digest/preview", "get"),
        ("/api/v1/exports/day.csv", "get"),
        ("/api/v1/exports/history.csv", "get"),
        ("/api/v1/clients/{client_id}/export.csv", "get"),
    ):
        assert method in paths[path], (method, path)
    for path in (
        "/api/v1/exports/day.csv",
        "/api/v1/exports/history.csv",
        "/api/v1/clients/{client_id}/export.csv",
    ):
        answer = paths[path]["get"]["responses"]["200"]
        assert list(answer["content"]) == ["text/csv"]
    ribbon = paths["/api/v1/dashboard/ribbon"]["get"]
    names = {parameter["name"] for parameter in ribbon["parameters"]}
    assert names == {"from", "to", "problems_only"}


def test_the_dashboard_schemas_have_the_chapter_fields() -> None:
    schemas = generate()["components"]["schemas"]

    def fields(name: str) -> set[str]:
        return set(schemas[name]["properties"])

    assert fields("DashboardToday") == {
        "generated_at",
        "stats",
        "coverage",
        "attention",
        "heartbeat",
        "demo_seeded",
    }
    assert fields("Stats") == {"verified", "failed", "silent", "unmatched", "paused"}
    assert fields("Stat") == {"value", "delta_vs_yesterday", "spark14"}
    assert fields("Coverage") == {"verified", "expected", "ratio"}
    assert fields("AttentionItem") >= {
        "client_id",
        "client_name",
        "job_id",
        "job_name",
        "state",
        "expected_by",
        "last_success_at",
        "raw_message_id",
    }
    assert fields("HeartbeatOut") == {"at", "age_seconds", "stale"}
    assert fields("Ribbon") == {"window", "morning_line_at", "clients"}
    assert fields("RibbonWindow") == {"from", "to"}
    assert fields("RibbonClient") == {"id", "name", "jobs"}
    assert fields("RibbonJob") == {"id", "name", "occurrences"}
    assert fields("RibbonOccurrence") == {
        "scheduled_for",
        "deadline",
        "state",
        "result_at",
    }
    assert fields("TrendDay") == {"date", "verified", "failed", "silent"}
    assert fields("BreakdownItem") == {"key", "label", "verified", "failed", "silent"}
    assert fields("ActivityItem") >= {"at", "kind", "summary", "ref_kind", "ref_id"}
    assert fields("DigestPreview") >= {"subject", "html", "text"}
    assert fields("QueueStatus") == {
        "pending_messages",
        "pending_notifications",
        "failed_notifications",
    }
    assert {"evaluator_lag_seconds", "extension_api_level"} <= fields("SystemStatus")
