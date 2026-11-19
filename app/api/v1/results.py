"""results: list reported runs, all of them or one job's.

Admins and technicians, or an API token of scope read. Phase C4-I adds POST
results (ingest token) to this router.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import Principal
from app.api.deps import DbDep, ReaderDep, Services, ServicesDep
from app.api.pagination import (
    DEFAULT_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_time_cursor,
    encode_time_cursor,
)
from app.api.problems import ProblemError
from app.api.v1.ingest_schemas import ResultOut, ResultPage
from app.ingest.results import ResultStatus
from app.repos.jobs import JobRepository
from app.repos.results import JobResultRepository

router = APIRouter(tags=["results"])

StatusQuery = Annotated[ResultStatus | None, Query()]


async def result_page(
    services: Services,
    db: AsyncSession,
    principal: Principal,
    *,
    job_id: uuid.UUID | None,
    status: ResultStatus | None,
    cursor: str | None,
    limit: int,
) -> ResultPage:
    after = None if cursor is None else decode_time_cursor(cursor, "received_at")
    results = JobResultRepository(db, services.policy)
    found = await results.page(
        principal, job_id=job_id, status=status, after=after, limit=limit + 1
    )
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        last = items[-1]
        next_cursor = encode_time_cursor("received_at", last.received_at, last.id)
    return ResultPage(
        items=[ResultOut.model_validate(result) for result in items],
        next_cursor=next_cursor,
    )


@router.get("/results")
async def list_results(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    job_id: uuid.UUID | None = None,
    status: StatusQuery = None,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> ResultPage:
    """Results, newest first; job_id and status narrow the list."""
    return await result_page(
        services,
        db,
        principal,
        job_id=job_id,
        status=status,
        cursor=cursor,
        limit=limit,
    )


@router.get("/jobs/{job_id}/results")
async def list_job_results(
    job_id: uuid.UUID,
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    status: StatusQuery = None,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> ResultPage:
    """One job's results, newest first; 404 for an unknown job."""
    if await JobRepository(db, services.policy).get(principal, job_id) is None:
        raise ProblemError(404, "Job not found")
    return await result_page(
        services,
        db,
        principal,
        job_id=job_id,
        status=status,
        cursor=cursor,
        limit=limit,
    )
