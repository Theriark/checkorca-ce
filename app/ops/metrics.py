"""Prometheus metrics (phase C10): /metrics behind METRICS_TOKEN.

Six checkorca_ metrics on a registry of their own (no process or Python
collectors: the endpoint answers nothing else):

- checkorca_messages_received_total: every accepted message on every
  channel, duplicates included (app/ingest/store.py).
- checkorca_results_total{status}: every stored result, by its status
  (success, warning, failed, started, unknown).
- checkorca_unmatched: the results no job is bound to right now.
- checkorca_evaluator_lag_seconds: how long the oldest evaluation the
  evaluator owes has waited (the system/status value).
- checkorca_notification_failures_total: notifications that failed for good
  after the retry ladder (app/notify/dispatcher.py).
- checkorca_heartbeat_age_seconds: the age of the worker heartbeat; NaN
  before the first tick.

The counters live in the process that does the work. ROLE=all (the Dokploy
default) runs web and worker in one process, so one /metrics holds them all.
The Docker Compose install runs web and worker in two containers, and its
scrapes see the web side only (results by ping and the results API); the
gauges are complete either way, because they are read from the database on
every scrape.

Access: Authorization: Bearer <METRICS_TOKEN>, compared in constant time.
Without METRICS_TOKEN (the safe default) every scrape is refused with 401,
and so is a wrong token; the token is a secret (app/settings.py) and never
appears in a log line.
"""

import secrets
from datetime import timedelta
from typing import Final

from fastapi import APIRouter, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    generate_latest,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import SYSTEM
from app.api.deps import Services, ServicesDep
from app.repos.dashboard import DashboardRepository
from app.repos.heartbeat import HeartbeatRepository
from app.repos.results import JobResultRepository
from app.worker.heartbeat import heartbeat_view

__all__ = [
    "MESSAGES_RECEIVED",
    "NOTIFICATION_FAILURES",
    "RESULTS",
    "registry",
    "refresh_gauges",
    "router",
]

registry: Final = CollectorRegistry()
MESSAGES_RECEIVED: Final = Counter(
    "checkorca_messages_received_total",
    "Messages accepted on every channel, duplicates included.",
    registry=registry,
)
RESULTS: Final = Counter(
    "checkorca_results_total",
    "Results stored, by status.",
    ("status",),
    registry=registry,
)
UNMATCHED: Final = Gauge(
    "checkorca_unmatched",
    "Results no job is bound to.",
    registry=registry,
)
EVALUATOR_LAG: Final = Gauge(
    "checkorca_evaluator_lag_seconds",
    "How long the oldest evaluation the evaluator owes has waited.",
    registry=registry,
)
NOTIFICATION_FAILURES: Final = Counter(
    "checkorca_notification_failures_total",
    "Notifications that failed for good after the retry ladder.",
    registry=registry,
)
HEARTBEAT_AGE: Final = Gauge(
    "checkorca_heartbeat_age_seconds",
    "The age of the worker heartbeat.",
    registry=registry,
)

router = APIRouter()


async def refresh_gauges(db: AsyncSession, services: Services) -> None:
    """Read the three gauge values from the database (once per scrape)."""
    now = services.clock.now()
    unmatched = await JobResultRepository(db, services.policy).unmatched_count(SYSTEM)
    UNMATCHED.set(unmatched)
    oldest = await DashboardRepository(db, services.policy).oldest_due(SYSTEM, now=now)
    lag = timedelta(0) if oldest is None else max(now - oldest, timedelta(0))
    EVALUATOR_LAG.set(lag.total_seconds())
    row = await HeartbeatRepository(db, services.policy).get(SYSTEM)
    age = heartbeat_view(row, now).age_seconds
    HEARTBEAT_AGE.set(float("nan") if age is None else age)


@router.get("/metrics")
async def metrics(request: Request, services: ServicesDep) -> Response:
    """The Prometheus exposition; 401 without the bearer token."""
    expected = services.settings.metrics_token.get_secret_value()
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if not expected or scheme.lower() != "bearer":
        return _refused()
    try:
        given = value.strip().encode()
    except UnicodeEncodeError:
        return _refused()
    if not secrets.compare_digest(given, expected.encode()):
        return _refused()
    async with services.sessionmaker() as db:
        await refresh_gauges(db, services)
    return Response(content=generate_latest(registry), media_type=CONTENT_TYPE_LATEST)


def _refused() -> Response:
    return Response(
        content="Not authorized.\n",
        status_code=401,
        headers={"WWW-Authenticate": "Bearer"},
    )
