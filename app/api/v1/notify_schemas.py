"""Request and response bodies of the notification routes (phase C9-B):
channels, channel rules, notifications and the digest settings.

docs/notifications.md is the contract for C9-F (the /notifications pages) and
C9-I (the slack, teams and webhook kinds). A channel's config is the kind's
settings, checked by the kind; its secret is write-only (D-6): answers carry
secret_set and a masked hint, never the secret.
"""

import json
import uuid
from datetime import date, datetime
from functools import lru_cache
from typing import Annotated, Any, Literal, Self
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, Field, model_validator

from app.api.v1.schemas import Body, Label

ChannelKindName = Literal["email", "slack", "teams", "webhook"]
ChannelStatus = Literal["sent", "failed"]
RuleScope = Literal["all", "client", "job"]
RuleEvent = Literal["failing", "missed", "warning", "recovered", "digest"]
NotificationEvent = Literal[
    "failing", "missed", "warning", "recovered", "reminder", "digest"
]
NotificationStatus = Literal["queued", "sent", "retrying", "failed"]
TargetAllowedBy = Literal["public", "allowed_host", "allow_private"]

MAX_SECRET_LENGTH = 2000
MAX_CONFIG_LENGTH = 10_000
MAX_URL_LENGTH = 2000


def small_config(value: dict[str, Any]) -> dict[str, Any]:
    """A config of at most MAX_CONFIG_LENGTH characters as JSON."""
    if len(json.dumps(value, default=str)) > MAX_CONFIG_LENGTH:
        raise ValueError(f"must be at most {MAX_CONFIG_LENGTH} characters as JSON")
    return value


def unique_events(values: list[str]) -> list[str]:
    """Events without repeats, in the given order."""
    return list(dict.fromkeys(values))


@lru_cache(maxsize=1)
def zone_names() -> frozenset[str]:
    return frozenset(available_timezones())


def known_zone(value: str) -> str:
    if value not in zone_names():
        raise ValueError("must be an IANA time zone such as Europe/Lisbon")
    return value


Config = Annotated[dict[str, Any], AfterValidator(small_config)]
Secret = Annotated[str, Field(max_length=MAX_SECRET_LENGTH)]
Events = Annotated[
    list[RuleEvent], Field(min_length=1, max_length=5), AfterValidator(unique_events)
]
# HH:MM, 24-hour clock.
DigestTime = Annotated[str, Field(pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$")]
ZoneName = Annotated[
    str, Field(min_length=1, max_length=64), AfterValidator(known_zone)
]


class NewChannel(Body):
    """A channel. config is the kind's settings (docs/notifications.md);
    secret is its credential (the relay password), stored encrypted."""

    kind: ChannelKindName
    label: Label
    enabled: bool = True
    config: Config = {}
    secret: Secret | None = None


class ChannelPatch(Body):
    """Only the fields sent change. config keys sent replace the stored ones
    (a null removes the key) and the result is checked again. A secret sent
    replaces the stored one; an empty secret removes it. Changing a setting
    that decides where the secret goes needs the secret again (422)."""

    label: Label | None = None
    enabled: bool | None = None
    config: Config | None = None
    secret: Secret | None = None


class ChannelOut(BaseModel):
    id: uuid.UUID
    kind: ChannelKindName
    label: str
    enabled: bool
    config: dict[str, Any]
    # False while the kind is not registered (C9-I adds slack, teams, webhook):
    # such a channel can only be listed and deleted.
    available: bool
    # What the secret is for (Relay password); null for an unknown kind.
    secret_label: str | None
    secret_set: bool
    secret_hint: str | None
    # The newest real delivery: sent or failed, when, and why it failed.
    last_status: ChannelStatus | None
    last_status_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class ChannelPage(BaseModel):
    items: list[ChannelOut]
    next_cursor: str | None


class ChannelTestResult(BaseModel):
    """ok: the test message was delivered; detail says what happened."""

    ok: bool
    detail: str


class TargetCheck(Body):
    url: Annotated[str, Field(min_length=1, max_length=MAX_URL_LENGTH)]


class TargetCheckResult(BaseModel):
    """The URL may be called: its host, port, the addresses it resolves to
    and why it is allowed. A refused URL answers 422 with the reason."""

    ok: bool
    host: str
    port: int
    addresses: list[str]
    allowed_by: TargetAllowedBy


class NewRule(Body):
    """scope all covers every job (scope_id null); client and job need the
    client's or the job's id. digest is for scope all only."""

    channel_id: uuid.UUID
    scope: RuleScope = "all"
    scope_id: uuid.UUID | None = None
    events: Events


class RulePatch(Body):
    """Only the fields sent change; the result is checked as a new rule."""

    scope: RuleScope | None = None
    scope_id: uuid.UUID | None = None
    events: Events | None = None


class RuleOut(BaseModel):
    id: uuid.UUID
    channel_id: uuid.UUID
    scope: RuleScope
    scope_id: uuid.UUID | None
    # The client ("Client") or job ("Client / Job") of the scope.
    scope_name: str | None
    events: list[RuleEvent]
    created_at: datetime


class RulePage(BaseModel):
    items: list[RuleOut]
    next_cursor: str | None


class NotificationOut(BaseModel):
    """One notification: about a flip (failing, missed, warning, recovered,
    reminder; flip_id, job and client set) or the digest of digest_day."""

    id: uuid.UUID
    channel_id: uuid.UUID
    channel_label: str
    channel_kind: ChannelKindName
    event: NotificationEvent
    status: NotificationStatus
    attempts: int
    error: str | None
    flip_id: uuid.UUID | None
    job_id: uuid.UUID | None
    job_name: str | None
    client_id: uuid.UUID | None
    client_name: str | None
    digest_day: date | None
    created_at: datetime
    last_attempt_at: datetime | None
    next_attempt_at: datetime | None
    sent_at: datetime | None


class NotificationPage(BaseModel):
    items: list[NotificationOut]
    next_cursor: str | None


class DigestSettingsOut(BaseModel):
    """When the daily digest goes out (HH:MM in the zone) and whether a
    24-hour reminder follows a failing or missed job."""

    digest_time_local: str
    digest_timezone: str
    reminder_24h: bool


class DigestSettingsPatch(Body):
    """Only the fields sent change; at least one must be sent."""

    digest_time_local: DigestTime | None = None
    digest_timezone: ZoneName | None = None
    reminder_24h: bool | None = None

    @model_validator(mode="after")
    def _not_empty(self) -> Self:
        if not self.model_fields_set:
            raise ValueError("send at least one field")
        return self
