"""The /api/v1 routes. Errors are problem documents (app/api/problems.py)."""

from fastapi import APIRouter

from app.api.problems import PROBLEM_RESPONSES
from app.api.v1 import auth, clients, jobs, schedule, tokens, users

router = APIRouter(prefix="/api/v1", responses=PROBLEM_RESPONSES)
router.include_router(auth.router)
router.include_router(users.router)
router.include_router(tokens.router)
router.include_router(clients.router)
router.include_router(jobs.router)
router.include_router(schedule.router)
