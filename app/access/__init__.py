"""Who is asking (Principal) and what they may do (AccessPolicy).

Every repository method takes a Principal and asks the AccessPolicy before it
touches the database (app/repos/base.py). CE ships AllowAllPolicy: everything a
signed-in principal can reach is allowed, and the role rules (users, tokens and
settings are admin only) sit on the API routes. EE replaces the policy with
per-client scopes (rnd-report-2 5.3 and 7.1) without changing a repository.
"""

from dataclasses import dataclass
from typing import Literal, Protocol, cast
from uuid import UUID

from sqlalchemy import Select

PrincipalKind = Literal["user", "token", "system"]
Role = Literal["admin", "technician"]
TokenScope = Literal["ingest", "read"]

ROLES: tuple[Role, ...] = ("admin", "technician")
TOKEN_SCOPES: tuple[TokenScope, ...] = ("ingest", "read")


def as_role(value: str) -> Role:
    """A stored role, checked; the database constraint allows only these two."""
    if value not in ROLES:
        raise ValueError("unknown role")
    return cast(Role, value)


def as_scope(value: str) -> TokenScope:
    """A stored token scope, checked."""
    if value not in TOKEN_SCOPES:
        raise ValueError("unknown token scope")
    return cast(TokenScope, value)


@dataclass(frozen=True, slots=True)
class Principal:
    """The caller: a signed-in user, an API token, or the system itself.

    The system principal is used by flows that run before anyone is signed in:
    sign-in, first run, session lookup and the development seed.
    """

    kind: PrincipalKind
    id: UUID | None = None
    role: Role | None = None
    scope: TokenScope | None = None

    @classmethod
    def for_user(cls, user_id: UUID, role: Role) -> "Principal":
        return cls(kind="user", id=user_id, role=role)

    @classmethod
    def for_token(cls, token_id: UUID, scope: TokenScope) -> "Principal":
        return cls(kind="token", id=token_id, scope=scope)

    @property
    def is_admin(self) -> bool:
        return self.kind == "user" and self.role == "admin"

    @property
    def actor(self) -> str:
        """The audit actor: "user:<id>", "token:<id>" or "system"."""
        if self.kind == "system":
            return "system"
        return f"{self.kind}:{self.id}"


SYSTEM = Principal(kind="system")


@dataclass(frozen=True, slots=True)
class Action:
    """What a repository method does: the resource and the verb."""

    resource: str
    verb: str


class AccessDenied(Exception):
    """The access policy refused an action. The API answers 403."""


class AccessPolicy(Protocol):
    """Decides every repository call (seam frozen in phase C12)."""

    def check(self, principal: Principal, action: Action) -> None:
        """Return when the action is allowed; raise AccessDenied otherwise."""
        ...

    def scope[S: Select](self, principal: Principal, resource: str, query: S) -> S:
        """Narrow a list query to the rows the principal may see."""
        ...


class AllowAllPolicy:
    """The CE policy: every action of an authenticated principal is allowed."""

    def check(self, principal: Principal, action: Action) -> None:
        return None

    def scope[S: Select](self, principal: Principal, resource: str, query: S) -> S:
        return query
