"""The client delete map: every row that belongs to a client, in delete order.

DELETE /clients/{id} removes the client and all of these rows in one
transaction (legal D-3). No foreign key to client cascades, so a table that
references a client (directly or through a job) and is missing here makes the
delete fail rather than leave rows behind; tests/repos/test_client_delete.py
also fails until the table is added.

Every later table that holds client data joins this map in its own phase:
add a step before the steps of the tables it references. A table that names a
client or a job without a foreign key (channel_rule.scope_id, phase C9) is
listed in SCOPED_TABLES, so the test still finds it. channel holds no client
data and is not in the map.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from sqlalchemy import ColumnElement, and_, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.db.base import Base
from app.db.models import (
    ChannelRule,
    Client,
    Flip,
    Job,
    JobResult,
    JobStateRecord,
    Notification,
    Occurrence,
    RawMessage,
)

# Tables that hold a client's or a job's id without a foreign key.
SCOPED_TABLES: Final = frozenset({"channel_rule"})

type DeleteRows = Callable[[uuid.UUID], ColumnElement[bool]]


@dataclass(frozen=True, slots=True)
class DeleteStep:
    """The rows of one table that belong to the client with the given id."""

    model: type[Base]
    rows: DeleteRows


def _client_results(client_id: uuid.UUID) -> ColumnElement[bool]:
    """Results of the client's jobs, and results of the client's messages."""
    jobs = select(Job.id).where(Job.client_id == client_id)
    messages = select(RawMessage.id).where(RawMessage.client_id == client_id)
    return or_(JobResult.job_id.in_(jobs), JobResult.raw_message_id.in_(messages))


def _client_flips(client_id: uuid.UUID) -> ColumnElement[bool]:
    """Flips made while the job was the client's, and flips of the client's
    jobs (a job moved from another client keeps its earlier flips)."""
    jobs = select(Job.id).where(Job.client_id == client_id)
    return or_(Flip.client_id == client_id, Flip.job_id.in_(jobs))


def _client_jobs(column: InstrumentedAttribute[uuid.UUID]) -> DeleteRows:
    """The rows whose job is one of the client's."""

    def rows(client_id: uuid.UUID) -> ColumnElement[bool]:
        return column.in_(select(Job.id).where(Job.client_id == client_id))

    return rows


def _client_notifications(client_id: uuid.UUID) -> ColumnElement[bool]:
    """Notifications about the client's flips (the digest names no client)."""
    flips = select(Flip.id).where(_client_flips(client_id))
    return Notification.flip_id.in_(flips)


def _client_rules(client_id: uuid.UUID) -> ColumnElement[bool]:
    """Rules for the client, and rules for one of its jobs."""
    jobs = select(Job.id).where(Job.client_id == client_id)
    return or_(
        and_(ChannelRule.scope == "client", ChannelRule.scope_id == client_id),
        and_(ChannelRule.scope == "job", ChannelRule.scope_id.in_(jobs)),
    )


CLIENT_DELETE_MAP: tuple[DeleteStep, ...] = (
    DeleteStep(Notification, _client_notifications),
    DeleteStep(ChannelRule, _client_rules),
    DeleteStep(Flip, _client_flips),
    DeleteStep(Occurrence, _client_jobs(Occurrence.job_id)),
    DeleteStep(JobStateRecord, _client_jobs(JobStateRecord.job_id)),
    DeleteStep(JobResult, _client_results),
    DeleteStep(RawMessage, lambda client_id: RawMessage.client_id == client_id),
    DeleteStep(Job, lambda client_id: Job.client_id == client_id),
    DeleteStep(Client, lambda client_id: Client.id == client_id),
)


async def delete_client_rows(db: AsyncSession, client_id: uuid.UUID) -> None:
    """Run every step in the caller's transaction (call through the repository,
    which asks the access policy first, after it locked the client).

    The client's jobs are locked first, after the client: an evaluator batch
    that is writing rows for them holds the client and the jobs FOR KEY SHARE
    (app/repos/evaluation.py claim), so it commits before the steps run and
    its rows are deleted too; a batch that starts later skips the locked
    rows. A job moved to this client after the batch read it is covered by
    its job lock."""
    await db.execute(
        select(Job.id)
        .where(Job.client_id == client_id)
        .order_by(Job.id)
        .with_for_update()
    )
    for step in CLIENT_DELETE_MAP:
        await db.execute(delete(step.model).where(step.rows(client_id)))
