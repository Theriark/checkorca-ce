"""/metrics (phase C10): six checkorca_ metrics behind METRICS_TOKEN.

The counters live in the process that does the work; the gauges are read
from the database on every scrape. Without METRICS_TOKEN (the safe default)
or with a wrong token every scrape answers 401.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from prometheus_client import generate_latest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.ingest.results import ParsedResult
from app.ingest.store import record_result
from app.main import create_app
from app.ops import metrics
from app.repos.heartbeat import HeartbeatRepository
from app.settings import load_settings
from helpers import FakeClock, running

TOKEN = "ci-metrics-token-not-a-real-secret"
NOW = datetime(2027, 1, 4, 9, tzinfo=UTC)
NAMES = (
    "checkorca_messages_received_total",
    "checkorca_results_total",
    "checkorca_unmatched",
    "checkorca_evaluator_lag_seconds",
    "checkorca_notification_failures_total",
    "checkorca_heartbeat_age_seconds",
)


def test_the_exposition_answers_the_six_metric_names() -> None:
    """The metric name snapshot: exactly the six names, nothing else."""
    text = generate_latest(metrics.registry).decode()
    for name in NAMES:
        assert f"\n{name} " in text or text.startswith(f"{name} ")
    assert "python_gc_" not in text
    assert "process_cpu" not in text


@pytest.fixture
def app(
    db_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> FastAPI:
    monkeypatch.setenv("METRICS_TOKEN", TOKEN)
    return create_app(load_settings(), static_dir=None, clock=clock)


async def test_metrics_is_refused_without_a_token() -> None:
    """The safe default: no METRICS_TOKEN in the environment, always 401."""
    async with running(create_app(load_settings(), static_dir=None)) as client:
        plain = await client.get("/metrics")
        assert plain.status_code == 401
        assert plain.headers["www-authenticate"] == "Bearer"
        bearer = await client.get(
            "/metrics", headers={"Authorization": f"Bearer {TOKEN}"}
        )
        assert bearer.status_code == 401


async def test_metrics_is_refused_with_a_wrong_token(client) -> None:
    wrong = await client.get(
        "/metrics", headers={"Authorization": "Bearer not-the-token"}
    )
    assert wrong.status_code == 401
    assert wrong.headers["www-authenticate"] == "Bearer"


async def test_metrics_answers_with_the_token(client) -> None:
    response = await client.get(
        "/metrics", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    for name in NAMES:
        assert name in body


async def test_the_gauges_read_the_database(
    client,
    db_engine: AsyncEngine,
    clock: FakeClock,
) -> None:
    """One unmatched result makes the gauge 1; a fresh heartbeat has age 0;
    with no job to evaluate the evaluator lag is 0."""
    policy = AllowAllPolicy()
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        await record_result(
            db,
            policy,
            SYSTEM,
            ParsedResult(status="failed", job_name="Unknown job"),
            received_at=clock.now(),
        )
        await HeartbeatRepository(db, policy).beat(
            SYSTEM,
            at=clock.now(),
            holder="test-host pid 1",
            started_at=clock.now(),
        )
        await db.commit()
    response = await client.get(
        "/metrics", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    assert "checkorca_unmatched 1.0" in response.text
    assert "checkorca_evaluator_lag_seconds 0.0" in response.text
    assert "checkorca_heartbeat_age_seconds 0.0" in response.text


async def test_the_lag_gauge_is_the_age_of_the_oldest_owed_evaluation(
    client,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An evaluation owed for 90 seconds makes the lag gauge 90."""
    owed = clock.now() - timedelta(seconds=90)

    async def oldest_due(
        self: object, principal: object, *, now: datetime
    ) -> datetime:
        return owed

    monkeypatch.setattr(metrics.DashboardRepository, "oldest_due", oldest_due)
    response = await client.get(
        "/metrics", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    assert "checkorca_evaluator_lag_seconds 90.0" in response.text


async def test_counters_count_stored_results_by_status(
    db_engine: AsyncEngine,
) -> None:
    """record_result moves the per-status counters (store_raw moves the
    message counter on every channel, duplicates included)."""
    before = metrics.registry.get_sample_value(
        "checkorca_results_total", {"status": "failed"}
    )
    policy = AllowAllPolicy()
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        await record_result(
            db,
            policy,
            SYSTEM,
            ParsedResult(status="failed"),
            received_at=NOW,
        )
        await db.commit()
    after = metrics.registry.get_sample_value(
        "checkorca_results_total", {"status": "failed"}
    )
    assert after == (before or 0.0) + 1.0


async def test_a_scrape_before_any_heartbeat_reports_nan(client) -> None:
    response = await client.get(
        "/metrics", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 200
    assert "checkorca_heartbeat_age_seconds NaN" in response.text
