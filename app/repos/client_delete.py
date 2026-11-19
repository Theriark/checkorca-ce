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

from sqlalchemy import ColumnElement, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import Client, Job


@dataclass(frozen=True, slots=True)
class DeleteStep:
    """The rows of one table that belong to the client with the given id."""

    model: type[Base]
    rows: Callable[[uuid.UUID], ColumnElement[bool]]


CLIENT_DELETE_MAP: tuple[DeleteStep, ...] = (
    DeleteStep(Job, lambda client_id: Job.client_id == client_id),
    DeleteStep(Client, lambda client_id: Client.id == client_id),
)


async def delete_client_rows(db: AsyncSession, client_id: uuid.UUID) -> None:
    """Run every step in the caller's transaction (call through the repository,
    which asks the access policy first)."""
    for step in CLIENT_DELETE_MAP:
        await db.execute(delete(step.model).where(step.rows(client_id)))
