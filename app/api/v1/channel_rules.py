"""channel-rules: list, create, change and delete the rules that decide which
flips a channel hears about (phase C9-B).

A rule covers every job (scope all), the jobs of one client (scope client)
or one job (scope job), for the events failing, missed, warning and
recovered; the event digest sends the daily digest and needs scope all.
Admins change rules (signed in, X-CSRF-Token); admins and technicians, or an
API token of scope read, list them.
"""

import uuid
from typing import Any, cast

from fastapi import APIRouter, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.access import Principal
from app.api.deps import AdminDep, DbDep, ReaderDep, Services, ServicesDep, record_audit
from app.api.pagination import (
    DEFAULT_LIMIT,
    CursorQuery,
    LimitQuery,
    decode_time_cursor,
    encode_time_cursor,
)
from app.api.problems import FieldProblem, ProblemError
from app.api.v1.notify_schemas import (
    NewRule,
    RuleEvent,
    RuleOut,
    RulePage,
    RulePatch,
    RuleScope,
)
from app.db.models import ChannelRule
from app.repos.clients import ClientRepository
from app.repos.jobs import JobRepository
from app.repos.notifications import ChannelRepository, ChannelRuleRepository

router = APIRouter(prefix="/channel-rules", tags=["notifications"])


def rule_not_found() -> ProblemError:
    return ProblemError(404, "Rule not found")


def invalid_rule(field: str, message: str) -> ProblemError:
    return ProblemError(
        422,
        "Invalid rule",
        message,
        errors=[FieldProblem(field=f"body.{field}", message=message)],
    )


def rule_out(rule: ChannelRule, names: dict[uuid.UUID, str]) -> RuleOut:
    return RuleOut(
        id=rule.id,
        channel_id=rule.channel_id,
        scope=cast(RuleScope, rule.scope),
        scope_id=rule.scope_id,
        scope_name=None if rule.scope_id is None else names.get(rule.scope_id),
        events=[cast(RuleEvent, event) for event in rule.events],
        created_at=rule.created_at,
    )


async def described(
    services: Services, db: AsyncSession, principal: Principal, rule: ChannelRule
) -> RuleOut:
    names = await ChannelRuleRepository(db, services.policy).scope_names(
        principal, [rule]
    )
    return rule_out(rule, names)


async def check_rule(
    services: Services,
    db: AsyncSession,
    principal: Principal,
    scope: str,
    scope_id: uuid.UUID | None,
    events: list[str],
) -> None:
    """422 unless the scope fits its id and the events fit the scope. The
    client or job is locked, so a client delete running meanwhile either
    removes the new rule too or makes this one fail."""
    if scope == "all":
        if scope_id is not None:
            raise invalid_rule("scope_id", "A rule for all jobs has no scope_id.")
    elif scope_id is None:
        raise invalid_rule("scope_id", f"A rule for one {scope} needs its id.")
    elif scope == "client":
        clients = ClientRepository(db, services.policy)
        if await clients.get(principal, scope_id, for_update=True) is None:
            raise invalid_rule("scope_id", "No client with this id.")
    else:
        jobs = JobRepository(db, services.policy)
        if await jobs.get(principal, scope_id, for_update=True) is None:
            raise invalid_rule("scope_id", "No job with this id.")
    if "digest" in events and scope != "all":
        raise invalid_rule(
            "events", "The daily digest covers every job: use it with scope all."
        )


@router.get("")
async def list_rules(
    principal: ReaderDep,
    services: ServicesDep,
    db: DbDep,
    channel_id: uuid.UUID | None = None,
    cursor: CursorQuery = None,
    limit: LimitQuery = DEFAULT_LIMIT,
) -> RulePage:
    """Rules, oldest first; channel_id narrows them to one channel."""
    after = None if cursor is None else decode_time_cursor(cursor, "created_at")
    rules = ChannelRuleRepository(db, services.policy)
    found = await rules.page(
        principal, channel_id=channel_id, after=after, limit=limit + 1
    )
    items = found[:limit]
    next_cursor = None
    if len(found) > limit:
        last = items[-1]
        next_cursor = encode_time_cursor("created_at", last.created_at, last.id)
    names = await rules.scope_names(principal, items)
    return RulePage(
        items=[rule_out(rule, names) for rule in items], next_cursor=next_cursor
    )


@router.post("", status_code=201)
async def create_rule(
    body: NewRule,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> RuleOut:
    """Create a rule; 422 for an unknown channel, client or job."""
    principal = context.principal
    channel = await ChannelRepository(db, services.policy).get(
        principal, body.channel_id, for_update=True
    )
    if channel is None:
        raise invalid_rule("channel_id", "No channel with this id.")
    events = list(body.events)
    await check_rule(services, db, principal, body.scope, body.scope_id, events)
    rule = await ChannelRuleRepository(db, services.policy).create(
        principal,
        channel_id=channel.id,
        scope=body.scope,
        scope_id=body.scope_id,
        events=events,
        now=services.clock.now(),
    )
    await record_audit(
        services,
        db,
        request,
        principal.actor,
        "channel_rule.create",
        target_kind="channel_rule",
        target_id=rule.id,
        scope=body.scope,
    )
    await db.commit()
    return await described(services, db, principal, rule)


@router.patch("/{rule_id}")
async def update_rule(
    rule_id: uuid.UUID,
    body: RulePatch,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> RuleOut:
    """Change the scope or the events. A new scope other than all needs its
    scope_id in the same request; scope all clears it."""
    principal = context.principal
    rules = ChannelRuleRepository(db, services.policy)
    rule = await rules.get(principal, rule_id, for_update=True)
    if rule is None:
        raise rule_not_found()
    sent = body.model_fields_set
    scope = body.scope or rule.scope
    if "scope_id" in sent:
        scope_id = body.scope_id
    elif scope == "all":
        scope_id = None
    else:
        scope_id = rule.scope_id if scope == rule.scope else None
    events = list(body.events) if body.events is not None else list(rule.events)
    await check_rule(services, db, principal, scope, scope_id, events)
    changes: dict[str, Any] = {
        field: value
        for field, value in (
            ("scope", scope),
            ("scope_id", scope_id),
            ("events", events),
        )
        if getattr(rule, field) != value
    }
    if changes:
        await rules.update(principal, rule, **changes)
        await record_audit(
            services,
            db,
            request,
            principal.actor,
            "channel_rule.update",
            target_kind="channel_rule",
            target_id=rule.id,
            fields=",".join(sorted(changes)),
        )
    await db.commit()
    return await described(services, db, principal, rule)


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: uuid.UUID,
    context: AdminDep,
    request: Request,
    services: ServicesDep,
    db: DbDep,
) -> None:
    rules = ChannelRuleRepository(db, services.policy)
    rule = await rules.get(context.principal, rule_id, for_update=True)
    if rule is None:
        raise rule_not_found()
    await rules.delete(context.principal, rule)
    await record_audit(
        services,
        db,
        request,
        context.principal.actor,
        "channel_rule.delete",
        target_kind="channel_rule",
        target_id=rule_id,
    )
    await db.commit()
