"""jobs/{job_id}/acknowledge (phase C8-B): someone is on the job's state.

Admins and technicians, signed in (X-CSRF-Token). Sets acknowledged_by and
acknowledged_at, audits job.acknowledge, and answers the job. The next flip
of the job state clears both (app/repos/evaluation.py), so a new state needs
a look again. The settings do not change, so updated_at stays.
"""

import uuid

from fastapi import APIRouter, Request

from app.api.deps import DbDep, ServicesDep, SessionDep, record_audit
from app.api.v1.job_schemas import JobOut
from app.api.v1.jobs import acknowledger_emails, job_out, load_job, state_record
from app.repos.dashboard import DashboardRepository

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("/{job_id}/acknowledge")
async def acknowledge_job(
    job_id: uuid.UUID,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> JobOut:
    """Acknowledge the job's state: someone is on it. The next flip of the
    job state clears it; 404 for an unknown job."""
    job, client = await load_job(services, db, context, job_id)
    now = services.clock.now()
    await DashboardRepository(db, services.policy).acknowledge(
        context.principal, job, user_id=context.user.id, at=now
    )
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "job.acknowledge",
        target_kind="job",
        target_id=job.id,
    )
    await db.commit()
    record = await state_record(services, db, context.principal, job)
    emails = await acknowledger_emails(services, db, context.principal, [job])
    return job_out(services, job, client.name, now, context.principal, record, emails)
