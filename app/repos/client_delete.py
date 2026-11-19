"""The client delete map: every row that belongs to a client, in delete order.

DELETE /clients/{id} removes the client and all of these rows in one
transaction (legal D-3). No foreign key to client cascades, so a table that
references a client (directly or through a job) and is missing here makes the
delete fail rather than leave rows behind; tests/repos/test_client_delete.py
also fails until the table is added.

Every later table that holds client data joins this map in its own phase:
add a step before the steps of the tables it references.
"""

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import ColumnElement, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import Client, Job, JobResult, RawMessage


@dataclass(frozen=True, slots=True)
class DeleteStep:
    """The rows of one table that belong to the client with the given id."""

    model: type[Base]
    rows: Callable[[uuid.UUID], ColumnElement[bool]]


def _client_results(client_id: uuid.UUID) -> ColumnElement[bool]:
    """Results of the client's jobs, and results of the client's messages."""
    jobs = select(Job.id).where(Job.client_id == client_id)
    messages = select(RawMessage.id).where(RawMessage.client_id == client_id)
    return or_(JobResult.job_id.in_(jobs), JobResult.raw_message_id.in_(messages))


CLIENT_DELETE_MAP: tuple[DeleteStep, ...] = (
    DeleteStep(JobResult, _client_results),
    DeleteStep(RawMessage, lambda client_id: RawMessage.client_id == client_id),
    DeleteStep(Job, lambda client_id: Job.client_id == client_id),
    DeleteStep(Client, lambda client_id: Client.id == client_id),
)


async def delete_client_rows(db: AsyncSession, client_id: uuid.UUID) -> None:
    """Run every step in the caller's transaction (call through the repository,
    which asks the access policy first)."""
    for step in CLIENT_DELETE_MAP:
        await db.execute(delete(step.model).where(step.rows(client_id)))
