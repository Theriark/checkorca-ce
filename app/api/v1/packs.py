"""packs: list, read, save, import, export, enable and disable parser packs;
packs/test, the test bench.

Admins and technicians alike (only users, tokens and settings are admin-only);
list, get and export also take an API token of scope read. Built-in packs are
read-only: they can be enabled, disabled and exported. A custom pack is saved
with PUT (or import) as Pack YAML; a pack that does not load answers 422 with
its issues (path and message, docs/parsers.md), and a changed pack must raise
its version.

packs/test runs the engine on a pasted mail in a child process of the web
process (app/api/bench.py), never in the worker and never on the web
process's own threads, with the engine's limits; it has its own rate limit
(per user) and body cap, and refuses a pack over the loader's 64 KiB.
"""

import asyncio
from typing import Annotated, Any, Final

from fastapi import APIRouter, File, Path, Request, UploadFile
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.bench import BenchUnavailable
from app.api.deps import (
    DbDep,
    ReaderDep,
    Services,
    ServicesDep,
    SessionContext,
    SessionDep,
    enforce_rate_limit,
    record_audit,
)
from app.api.pagination import (
    DEFAULT_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_cursor,
    encode_cursor,
)
from app.api.problems import FieldProblem, PackProblem, ProblemError
from app.api.v1.pack_schemas import (
    MAX_TEST_BODY,
    MAX_TEST_MAIL,
    PackBody,
    PackDetail,
    PackOut,
    PackPage,
    PackTestAnswer,
    PackTestRequest,
)
from app.parsers.loader import MAX_PACK_BYTES, PackInvalid, PackIssue, parse_pack
from app.parsers.model import Pack
from app.repos.packs import PackRepository

router = APIRouter(prefix="/packs", tags=["packs"])

PackIdPath = Annotated[
    str, Path(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$")
]
YAML_MEDIA_TYPE: Final = "application/yaml"
YAML_RESPONSE: Final[dict[int | str, dict[str, Any]]] = {
    200: {
        "content": {YAML_MEDIA_TYPE: {"schema": {"type": "string"}}},
        "description": "The Pack YAML as a file.",
    }
}
# packs/test reads its body itself (to cap it before parsing); the document
# still declares it.
TEST_BODY: Final[dict[str, Any]] = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {"schema": PackTestRequest.model_json_schema()}
        },
    }
}


def pack_not_found() -> ProblemError:
    return ProblemError(404, "Parser pack not found")


def pack_invalid(issues: tuple[PackIssue, ...]) -> ProblemError:
    return ProblemError(
        422,
        "Invalid parser pack",
        "Fix the issues listed; each names its place in the pack.",
        issues=[
            PackProblem(path=issue.path, message=issue.message) for issue in issues
        ],
    )


async def load_pack(text: str) -> Pack:
    """The compiled pack of the text (off the event loop), or 422 with its
    issues."""
    try:
        return await asyncio.to_thread(parse_pack, text)
    except PackInvalid as invalid:
        raise pack_invalid(invalid.issues) from None


@router.get("")
async def list_packs(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> PackPage:
    """Parser packs ordered by id, built-in and custom, without their YAML."""
    after = None if cursor is None else decode_cursor(cursor, ("id",))["id"]
    packs = PackRepository(db, services.policy)
    found = await packs.page(principal, after=after, limit=limit + 1)
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        next_cursor = encode_cursor({"id": items[-1].id})
    return PackPage(
        items=[PackOut.model_validate(pack) for pack in items], next_cursor=next_cursor
    )


async def save_pack(
    services: Services,
    db: AsyncSession,
    request: Request,
    response: Response,
    context: SessionContext,
    text: str,
    pack_id: str | None,
) -> PackDetail:
    """Save a custom pack: 422 for a pack that does not load or an id other
    than pack_id, 409 for a built-in id, 201 when it is new."""
    pack = await load_pack(text)
    if pack_id is not None and pack.id != pack_id:
        message = f"must be {pack_id!r}, the id in the URL"
        raise pack_invalid((PackIssue("/id", message),))
    packs = PackRepository(db, services.policy)
    stored = await packs.get(context.principal, pack.id, for_update=True)
    if stored is not None and stored.source == "builtin":
        raise built_in(pack.id)
    if stored is not None and stored.yaml == text:
        await db.commit()
        return PackDetail.model_validate(stored)
    if stored is not None and pack.version <= stored.version:
        message = f"must be higher than {stored.version}, the saved version"
        raise pack_invalid((PackIssue("/version", message),))
    now = services.clock.now()
    saved = await packs.save_custom(
        context.principal, pack, text, now, new=stored is None
    )
    if saved is None:
        await db.rollback()
        if stored is None:
            # Another save of this id came first; the version rule needs a retry.
            raise ProblemError(
                409,
                "Parser pack changed meanwhile",
                f"{pack.id} was saved by another request; load it and try again.",
            )
        raise built_in(pack.id)
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "pack.save",
        target_kind="parser_pack",
        target_id=pack.id,
        version=pack.version,
    )
    await db.commit()
    if stored is None:
        response.status_code = 201
    return PackDetail.model_validate(saved)


def built_in(pack_id: str) -> ProblemError:
    return ProblemError(
        409,
        "Built-in parser pack",
        f"{pack_id} ships with Checkorca-CE and cannot be changed; save a copy"
        " under another id and disable this one.",
    )


@router.post("/import")
async def import_pack(
    file: Annotated[UploadFile, File(description="The Pack YAML file.")],
    context: SessionDep,
    request: Request,
    response: Response,
    services: ServicesDep,
    db: DbDep,
) -> PackDetail:
    """Save a custom pack from a Pack YAML file, under the id it names; 201
    when it is new. The same rules as PUT."""
    data = await file.read(MAX_PACK_BYTES + 1)
    if len(data) > MAX_PACK_BYTES:
        message = f"a pack may have at most {MAX_PACK_BYTES} bytes"
        raise pack_invalid((PackIssue("", message),))
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise pack_invalid((PackIssue("", "the file is not UTF-8 text"),)) from None
    return await save_pack(services, db, request, response, context, text, None)


async def read_capped(request: Request, limit: int) -> bytes:
    """The request body, or 413 once it is longer than limit."""
    too_large = ProblemError(413, "Request too large", f"At most {limit} bytes.")
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise too_large
    body = bytearray()
    async for chunk in request.stream():
        body += chunk
        if len(body) > limit:
            raise too_large
    return bytes(body)


@router.post("/test", openapi_extra=TEST_BODY)
async def test_pack(
    context: SessionDep, request: Request, services: ServicesDep, db: DbDep
) -> PackTestAnswer:
    """Run the enabled packs, and the pack being edited, on a pasted mail:
    every pack's score, the pack that claims it and the results with their
    spans. 30 tests a minute per user; 503 when the bench does not answer
    within its time."""
    enforce_rate_limit(services.bench_limiter, f"user:{context.user.id}")
    try:
        body = PackTestRequest.model_validate_json(
            await read_capped(request, MAX_TEST_BODY)
        )
    except ValidationError as error:
        raise ProblemError(
            422,
            "Invalid request",
            "One or more fields are invalid.",
            errors=[
                FieldProblem(
                    field=".".join(["body", *(str(part) for part in item["loc"])]),
                    message=item["msg"],
                )
                for item in error.errors()
            ],
        ) from None
    raw = body.raw.encode("utf-8", "replace")
    if len(raw) > MAX_TEST_MAIL:
        raise ProblemError(413, "Mail too large", f"At most {MAX_TEST_MAIL} bytes.")
    if body.pack is not None:
        await load_pack(body.pack)
    texts = await services.pack_source.packs(db, services.policy, context.principal)
    # No connection is held while the child runs.
    await db.rollback()
    try:
        answer = await services.bench.run(
            [(text.id, text.yaml) for text in texts], body.pack, raw
        )
    except BenchUnavailable as error:
        raise ProblemError(503, "Test bench unavailable", str(error)) from None
    return PackTestAnswer.model_validate(answer)


@router.get("/{pack_id}")
async def get_pack(
    pack_id: PackIdPath, principal: ReaderDep, services: ServicesDep, db: DbDep
) -> PackDetail:
    pack = await PackRepository(db, services.policy).get(principal, pack_id)
    if pack is None:
        raise pack_not_found()
    return PackDetail.model_validate(pack)


@router.put("/{pack_id}")
async def put_pack(
    pack_id: PackIdPath,
    body: PackBody,
    context: SessionDep,
    request: Request,
    response: Response,
    services: ServicesDep,
    db: DbDep,
) -> PackDetail:
    """Create or replace a custom pack (201 when new). Built-in packs answer
    409; a changed pack must raise its version."""
    return await save_pack(services, db, request, response, context, body.yaml, pack_id)


@router.get("/{pack_id}/export", response_class=Response, responses=YAML_RESPONSE)
async def export_pack(
    pack_id: PackIdPath, principal: ReaderDep, services: ServicesDep, db: DbDep
) -> Response:
    """The pack as a Pack YAML file (import takes it back)."""
    pack = await PackRepository(db, services.policy).get(principal, pack_id)
    if pack is None:
        raise pack_not_found()
    return Response(
        content=pack.yaml.encode("utf-8"),
        media_type=f"{YAML_MEDIA_TYPE}; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{pack.id}.yaml"'},
    )


async def switch(
    services: Services,
    db: AsyncSession,
    request: Request,
    context: SessionContext,
    pack_id: str,
    enabled: bool,
) -> PackOut:
    packs = PackRepository(db, services.policy)
    pack = await packs.get(context.principal, pack_id, for_update=True)
    if pack is None:
        raise pack_not_found()
    if pack.enabled != enabled:
        await packs.set_enabled(context.principal, pack, enabled, services.clock.now())
        await record_audit(
            services,
            db,
            request,
            context.principal.actor,
            "pack.enable" if enabled else "pack.disable",
            target_kind="parser_pack",
            target_id=pack.id,
        )
    await db.commit()
    return PackOut.model_validate(pack)


@router.post("/{pack_id}/enable")
async def enable_pack(
    pack_id: PackIdPath,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> PackOut:
    """The pack parses mail again (from the worker's next tick)."""
    return await switch(services, db, request, context, pack_id, True)


@router.post("/{pack_id}/disable")
async def disable_pack(
    pack_id: PackIdPath,
    context: SessionDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> PackOut:
    """The pack stops parsing mail (from the worker's next tick)."""
    return await switch(services, db, request, context, pack_id, False)
