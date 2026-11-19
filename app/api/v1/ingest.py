"""The HTTP receivers (C4-I): raw mail, results, ping URLs and .eml upload.

- POST ingest/email/{inbox_code}: one raw RFC 822 message as the body, into
  an smtp or webhook inbox. Authorization: Bearer with an API token of scope
  ingest (any such inbox), or a webhook inbox's own token (chki_..., that
  inbox only). A read token is refused (403).
- POST results: a run as JSON (ingest token).
- GET or POST ping/{ping_token}, ping/{ping_token}/start and /fail: the job's
  ping URL records success, started or failed. The token in the URL is the
  credential, as with Healthchecks-style URLs, so a GET records a result too.
- POST messages/upload: an .eml file for an inbox, signed in (CSRF).

The token routes read no cookie: the credential is the Authorization header
or the URL, which a cross-site form cannot send or does not know, so they
need no CSRF token (tests/api/test_csrf_api.py, TOKEN_ROUTES). Each token
has 120 requests a minute (the token limiter, per API token, webhook inbox
and ping URL; only a known credential spends a bucket). Every message goes
through accept_message (app/ingest/receive.py): 5 MB with at most 256 KB of
headers, the inbox's sender rules, one row per duplicate. Answers are 202:
the worker parses the message later.
"""

import uuid
from typing import Annotated, Any, Final, Literal

from fastapi import APIRouter, Depends, File, Form, Path, Request, UploadFile
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import SYSTEM, Principal
from app.api.deps import (
    DbDep,
    Services,
    ServicesDep,
    SessionDep,
    enforce_rate_limit,
    record_audit,
    require_token,
)
from app.api.problems import ProblemError
from app.api.v1.ingest_schemas import MessageAccepted, NewResult, ResultAccepted
from app.db.models import Inbox, Job
from app.ingest.receive import MessageRefused, accept_message, check_size, is_mail
from app.ingest.results import ParsedResult, ResultStatus
from app.ingest.store import (
    MAX_MESSAGE_BYTES,
    MessageTooLarge,
    ResultRejected,
    StoredRaw,
    record_result,
)
from app.repos.inboxes import InboxRepository
from app.repos.jobs import JobRepository
from app.security.tokens import INBOX_TOKEN_PREFIX

router = APIRouter(tags=["ingest"])

_ingest_token = require_token("ingest")
IngestDep = Annotated[Principal, Depends(_ingest_token)]
InboxCode = Annotated[str, Path(max_length=64)]
PingTokenPath = Annotated[str, Path(max_length=64, pattern=r"^[A-Za-z0-9]+$")]
# The body of POST ingest/email in the OpenAPI document: FastAPI reads the
# raw body itself, so it declares none.
RAW_MAIL_BODY: Final[dict[str, Any]] = {
    "requestBody": {
        "required": True,
        "content": {
            "message/rfc822": {"schema": {"type": "string", "format": "binary"}}
        },
    }
}
PING_STATUS: Final[dict[str, ResultStatus]] = {"start": "started", "fail": "failed"}
# The ping answer is text; declared here, so the 4XX answers stay problem
# documents (a text/plain response_class would file them as text/plain too).
PING_RESPONSE: Final[dict[int | str, dict[str, Any]]] = {
    200: {
        "content": {"text/plain": {"schema": {"type": "string"}}},
        "description": "OK: the result was recorded.",
    }
}


def inbox_not_found() -> ProblemError:
    return ProblemError(404, "Inbox not found")


async def ingest_inbox(
    request: Request, services: Services, db: AsyncSession, inbox_code: str
) -> tuple[Principal, Inbox]:
    """Who may write to the inbox of this code: an ingest token, or the
    webhook inbox's own token for its own inbox."""
    scheme, _, value = request.headers.get("authorization", "").partition(" ")
    value = value.strip()
    inboxes = InboxRepository(db, services.policy)
    if scheme.lower() == "bearer" and value.startswith(INBOX_TOKEN_PREFIX):
        inbox = await inboxes.find_by_token(SYSTEM, value)
        if inbox is None or inbox.kind != "webhook":
            raise ProblemError(
                401,
                "API token invalid",
                "The token is unknown or was rotated.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        enforce_rate_limit(services.token_limiter, f"inbox:{inbox.id}")
        if inbox.code != inbox_code.strip().lower():
            raise ProblemError(403, "The token is not valid for this inbox")
        return SYSTEM, inbox
    principal = await _ingest_token(request, services, db)
    found = await inboxes.find_by_code(principal, inbox_code, kinds=("smtp", "webhook"))
    if found is None:
        raise inbox_not_found()
    return principal, found


async def store_message(
    services: Services,
    db: AsyncSession,
    principal: Principal,
    inbox: Inbox,
    raw: bytes,
) -> StoredRaw:
    """accept_message with the HTTP answers: 413 above 5 MB or 256 KB of
    headers, or 422 for an empty body, something that is no e-mail message,
    or the inbox's sender rules."""
    try:
        check_size(raw)
    except MessageTooLarge as error:
        raise ProblemError(413, "Message too large", f"{error}.") from None
    if not is_mail(raw):
        raise ProblemError(
            422,
            "Not an e-mail message",
            "Send one RFC 822 message: headers, a blank line, then the body.",
        )
    try:
        return await accept_message(
            db,
            services.policy,
            principal,
            inbox=inbox,
            raw=raw,
            received_at=services.clock.now(),
        )
    except MessageTooLarge:
        raise ProblemError(413, "Message too large") from None
    except MessageRefused as error:
        raise ProblemError(422, "Message refused", str(error)) from None


@router.post("/ingest/email/{inbox_code}", status_code=202, openapi_extra=RAW_MAIL_BODY)
async def ingest_email(
    inbox_code: InboxCode, request: Request, services: ServicesDep, db: DbDep
) -> MessageAccepted:
    """Store one raw message (RFC 822 bytes as the body) in an smtp or webhook
    inbox; the same message twice is stored once (duplicate true)."""
    principal, inbox = await ingest_inbox(request, services, db, inbox_code)
    stored = await store_message(services, db, principal, inbox, await request.body())
    await db.commit()
    return MessageAccepted(message_id=stored.id, duplicate=stored.duplicate)


@router.post("/results", status_code=202)
async def create_result(
    body: NewResult, principal: IngestDep, services: ServicesDep, db: DbDep
) -> ResultAccepted:
    """Record a run. With job_id or ping_token the result belongs to that job
    (404 when there is none); with client_hint and job_name it waits for the
    matcher."""
    jobs = JobRepository(db, services.policy)
    job: Job | None = None
    if body.job_id is not None:
        job = await jobs.get(principal, body.job_id)
    elif body.ping_token is not None:
        job = await jobs.find_by_ping_token(principal, body.ping_token)
    if job is None and (body.job_id is not None or body.ping_token is not None):
        raise ProblemError(404, "Job not found")
    job_id = None if job is None else job.id
    result = ParsedResult(
        status=body.status,
        job_name=body.job_name,
        client_hint=body.client_hint,
        started_at=body.started_at,
        finished_at=body.finished_at,
        run_id=body.run_id,
        details=body.details,
    )
    try:
        result_id = await record_result(
            db,
            services.policy,
            principal,
            result,
            received_at=services.clock.now(),
            job_id=job_id,
        )
    except ResultRejected as error:
        raise ProblemError(422, "Result rejected", str(error)) from None
    await db.commit()
    return ResultAccepted(result_id=result_id, job_id=job_id)


async def ping(
    services: Services, db: AsyncSession, token: str, status: ResultStatus
) -> Response:
    job = await JobRepository(db, services.policy).find_by_ping_token(SYSTEM, token)
    if job is None:
        raise ProblemError(404, "Ping URL not found")
    # Only a known token spends a bucket, so unknown ones cannot push the
    # buckets of real tokens out of the limiter. Keyed by the job: the
    # limiter keeps no ping URL in memory.
    enforce_rate_limit(services.token_limiter, f"ping:{job.id}")
    await record_result(
        db,
        services.policy,
        SYSTEM,
        ParsedResult(status=status, details={"source": "ping"}),
        received_at=services.clock.now(),
        job_id=job.id,
    )
    await db.commit()
    return PlainTextResponse("OK")


@router.get("/ping/{ping_token}", response_class=Response, responses=PING_RESPONSE)
@router.post("/ping/{ping_token}", response_class=Response, responses=PING_RESPONSE)
async def ping_success(
    ping_token: PingTokenPath, services: ServicesDep, db: DbDep
) -> Response:
    """The job's run ended well; answers OK."""
    return await ping(services, db, ping_token, "success")


@router.get(
    "/ping/{ping_token}/{signal}", response_class=Response, responses=PING_RESPONSE
)
@router.post(
    "/ping/{ping_token}/{signal}", response_class=Response, responses=PING_RESPONSE
)
async def ping_signal(
    ping_token: PingTokenPath,
    signal: Literal["start", "fail"],
    services: ServicesDep,
    db: DbDep,
) -> Response:
    """start: the job's run began; fail: it failed. Answers OK."""
    return await ping(services, db, ping_token, PING_STATUS[signal])


@router.post("/messages/upload", status_code=202)
async def upload_message(
    file: Annotated[UploadFile, File(description="The message as an .eml file.")],
    inbox_id: Annotated[uuid.UUID, Form()],
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> MessageAccepted:
    """Store an uploaded .eml file in an inbox, as if it had been received."""
    inboxes = InboxRepository(db, services.policy)
    inbox = await inboxes.get(context.principal, inbox_id)
    if inbox is None:
        raise inbox_not_found()
    raw = await file.read(MAX_MESSAGE_BYTES + 1)
    stored = await store_message(services, db, context.principal, inbox, raw)
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "message.upload",
        target_kind="message",
        target_id=stored.id,
        inbox_id=str(inbox.id),
        duplicate=stored.duplicate,
    )
    await db.commit()
    return MessageAccepted(message_id=stored.id, duplicate=stored.duplicate)
