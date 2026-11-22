"""The /api/v1 routes. Errors are problem documents (app/api/problems.py)."""

from fastapi import APIRouter

from app.api.problems import PROBLEM_RESPONSES
from app.api.v1 import (
    acknowledge,
    auth,
    channel_rules,
    channels,
    clients,
    dashboard,
    evaluation,
    exports,
    inboxes,
    ingest,
    jobs,
    messages,
    notifications,
    packs,
    results,
    schedule,
    settings,
    system,
    tokens,
    unmatched,
    users,
)

router = APIRouter(prefix="/api/v1", responses=PROBLEM_RESPONSES)
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(tokens.router)
router.include_router(clients.router)
router.include_router(jobs.router)
router.include_router(acknowledge.router)
router.include_router(schedule.router)
router.include_router(inboxes.router)
router.include_router(messages.router)
router.include_router(results.router)
router.include_router(evaluation.router)
router.include_router(ingest.router)
router.include_router(packs.router)
router.include_router(unmatched.router)
router.include_router(system.router)
router.include_router(dashboard.router)
router.include_router(exports.router)
router.include_router(channels.router)
router.include_router(channel_rules.router)
router.include_router(notifications.router)
router.include_router(settings.router)
