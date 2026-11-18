"""AuditSink: where audit events go. CE writes them to the audit_event table.

An event names the actor, the action, the target by kind and id, and the client
address. Details hold ids, counts and field names, never content (legal D-7).
The sink writes in the caller's transaction, so an event exists exactly when
the change it records was committed. EE adds a hash-chained sink (rnd-report-2
7.1).
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditEvent

DetailValue = str | int | bool | None


@dataclass(frozen=True, slots=True)
class AuditRecord:
    at: datetime
    actor: str
    action: str
    target_kind: str | None = None
    target_id: str | None = None
    ip: str | None = None
    details: Mapping[str, DetailValue] = field(default_factory=dict)


class AuditSink(Protocol):
    async def record(self, db: AsyncSession, event: AuditRecord) -> None:
        """Add the event to the caller's transaction."""
        ...


class DatabaseAuditSink:
    """The CE sink: one audit_event row per event."""

    async def record(self, db: AsyncSession, event: AuditRecord) -> None:
        db.add(
            AuditEvent(
                at=event.at,
                actor=event.actor,
                action=event.action,
                target_kind=event.target_kind,
                target_id=event.target_id,
                ip=event.ip,
                details=dict(event.details),
            )
        )
