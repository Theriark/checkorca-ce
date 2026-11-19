"""schedule/preview: the next times of a schedule, or a readable error.

The job editor calls it on every change, so an unusable schedule is an answer
(error and field), not a failed request. Jobs are checked by the same rules
when they are saved (check_schedule).
"""

from datetime import datetime

from fastapi import APIRouter

from app.api.deps import ServicesDep, SessionDep
from app.api.problems import FieldProblem, ProblemError
from app.api.v1.job_schemas import SchedulePreview, SchedulePreviewRequest
from app.schedule import ScheduleError, ScheduleSpec, next_n, parse_spec

router = APIRouter(prefix="/schedule", tags=["schedule"])

NEVER_FIRES = "The schedule never fires in the next ten years."


def preview_spec(
    kind: str, expr: str, timezone: str, anchor: datetime, after: datetime, count: int
) -> tuple[ScheduleSpec, list[datetime]]:
    """The checked schedule and its next count times; ScheduleError otherwise."""
    spec = parse_spec(kind, expr, timezone, anchor)
    times = next_n(spec, after, count)
    if not times:
        raise ScheduleError("schedule_expr", NEVER_FIRES)
    return spec, times


def check_schedule(
    kind: str, expr: str, timezone: str, anchor: datetime, now: datetime
) -> ScheduleSpec:
    """The schedule of a job being saved; a 422 problem names the bad field."""
    try:
        spec, _ = preview_spec(kind, expr, timezone, anchor, now, 1)
    except ScheduleError as error:
        field = "schedule_expr" if error.field == "anchor" else error.field
        raise ProblemError(
            422,
            "Invalid schedule",
            error.message,
            errors=[FieldProblem(field=f"body.{field}", message=error.message)],
        ) from None
    return spec


@router.post("/preview")
async def preview_schedule(
    body: SchedulePreviewRequest, context: SessionDep, services: ServicesDep
) -> SchedulePreview:
    """The next count times after `after` (default now), in UTC and local time."""
    now = services.clock.now()
    after = body.after or now
    try:
        spec, times = preview_spec(
            body.kind,
            body.expr,
            body.timezone,
            body.anchor or after,
            after,
            body.count,
        )
    except ScheduleError as error:
        return SchedulePreview(
            next=[], local=[], error=error.message, field=error.field
        )
    zone = spec.zone
    return SchedulePreview(
        next=times,
        local=[time.astimezone(zone).isoformat() for time in times],
        error=None,
        field=None,
    )
