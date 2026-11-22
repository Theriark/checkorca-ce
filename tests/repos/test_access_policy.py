"""Every repository call passes the AccessPolicy, with the caller's Principal."""

import inspect
import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy import false

import app.repos.clients
import app.repos.evaluation
import app.repos.heartbeat
import app.repos.inboxes
import app.repos.jobs
import app.repos.messages
import app.repos.notifications
import app.repos.packs
import app.repos.results
import app.repos.sessions
import app.repos.settings
import app.repos.tokens
import app.repos.users
from app.access import (
    SYSTEM,
    AccessDenied,
    Action,
    AllowAllPolicy,
    Principal,
    as_role,
    as_scope,
)
from app.db.models import AppUser
from app.main import create_app
from app.repos.base import Repository, guarded, guarded_methods
from app.security.crypto import SecretBox
from app.settings import load_settings
from helpers import ADMIN_EMAIL, ADMIN_PASSWORD, TEST_FERNET_KEY, running, sign_in

# Importing the modules registers every repository class.
MODULES = (
    app.repos.clients,
    app.repos.evaluation,
    app.repos.heartbeat,
    app.repos.inboxes,
    app.repos.jobs,
    app.repos.messages,
    app.repos.notifications,
    app.repos.packs,
    app.repos.results,
    app.repos.sessions,
    app.repos.settings,
    app.repos.tokens,
    app.repos.users,
)


def repositories() -> list[type[Repository]]:
    found: list[type[Repository]] = []
    pending = list(Repository.__subclasses__())
    while pending:
        cls = pending.pop()
        found.append(cls)
        pending += cls.__subclasses__()
    return sorted(found, key=lambda cls: cls.__name__)


REPOSITORY_METHODS = [
    (cls, name) for cls in repositories() for name in sorted(guarded_methods(cls))
]


class DenyAllPolicy:
    def check(self, principal: Principal, action: Action) -> None:
        raise AccessDenied(f"{action.resource}.{action.verb}")

    def scope(self, principal: Principal, resource: str, query: Any) -> Any:
        raise AccessDenied(resource)


class RecordingPolicy(AllowAllPolicy):
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def check(self, principal: Principal, action: Action) -> None:
        self.calls.append((principal.kind, action.resource, action.verb))


class NoDatabase:
    """Any use of the database fails the test: the policy must refuse first."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"the database was used ({name}) before the policy")


def build(cls: type[Repository], policy: Any) -> Repository:
    if cls is app.repos.settings.SettingsRepository:
        return cls(NoDatabase(), policy, SecretBox(TEST_FERNET_KEY))
    return cls(NoDatabase(), policy)


def test_the_c1_to_c9_repositories_are_covered() -> None:
    names = {cls.__name__ for cls in repositories()}
    assert names >= {
        "UserRepository",
        "SessionRepository",
        "TokenRepository",
        "SettingsRepository",
        "ClientRepository",
        "JobRepository",
        "InboxRepository",
        "RawMessageRepository",
        "JobResultRepository",
        "HeartbeatRepository",
        "PackRepository",
        "EvaluationRepository",
        "OccurrenceRepository",
        "FlipRepository",
        "JobStateRepository",
        "ChannelRepository",
        "ChannelRuleRepository",
        "NotificationRepository",
    }
    assert len(REPOSITORY_METHODS) >= 95


@pytest.mark.parametrize(
    ("cls", "name"),
    REPOSITORY_METHODS,
    ids=[f"{cls.__name__}.{name}" for cls, name in REPOSITORY_METHODS],
)
async def test_every_method_asks_the_policy_before_the_database(
    cls: type[Repository], name: str
) -> None:
    repository = build(cls, DenyAllPolicy())
    method = getattr(repository, name)
    parameters = list(inspect.signature(method).parameters.values())
    # Bound method: the first parameter is the principal.
    assert parameters[0].name == "principal"
    arguments = {
        parameter.name: None
        for parameter in parameters[1:]
        if parameter.default is inspect.Parameter.empty
        and parameter.kind is not inspect.Parameter.VAR_KEYWORD
    }
    expected = f"{cls.resource}.{guarded_methods(cls)[name]}"
    with pytest.raises(AccessDenied, match=expected):
        await method(SYSTEM, **arguments)


async def test_a_call_without_a_principal_is_refused() -> None:
    repository = app.repos.users.UserRepository(NoDatabase(), AllowAllPolicy())
    with pytest.raises(TypeError, match="Principal"):
        await repository.count(None)


def test_an_unguarded_public_method_fails_at_import_time() -> None:
    async def everything(self: Repository) -> None:
        return None

    with pytest.raises(TypeError, match="must use @guarded"):
        type("Leaky", (Repository,), {"resource": "leaky", "everything": everything})


@pytest.mark.parametrize("wrap", [staticmethod, classmethod])
def test_a_public_static_or_class_method_fails_at_import_time(wrap: Any) -> None:
    async def make(*args: object) -> None:
        return None

    with pytest.raises(TypeError, match="must be a @guarded method"):
        type("Leaky", (Repository,), {"resource": "leaky", "make": wrap(make)})


class EmptyScopePolicy(AllowAllPolicy):
    """Allows every action but scopes every list query to nothing."""

    def scope(self, principal: Principal, resource: str, query: Any) -> Any:
        return query.where(false())


async def test_list_and_get_queries_go_through_the_policy_scope(
    db_engine: Any, admin: AppUser
) -> None:
    policy = EmptyScopePolicy()
    application = create_app(load_settings(), static_dir=None, policy=policy)
    async with running(application) as client:
        csrf = await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
        created = await client.post(
            "/api/v1/tokens",
            json={"label": "scoped away", "scope": "read"},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201
        assert (await client.get("/api/v1/users")).json()["items"] == []
        assert (await client.get("/api/v1/tokens")).json()["items"] == []
        user = await client.get(f"/api/v1/users/{admin.id}")
        assert user.status_code == 404
        revoke = await client.delete(
            f"/api/v1/tokens/{created.json()['id']}", headers={"X-CSRF-Token": csrf}
        )
        assert revoke.status_code == 404
        made = await client.post(
            "/api/v1/clients",
            json={"name": "Scoped Away Ltd"},
            headers={"X-CSRF-Token": csrf},
        )
        assert made.status_code == 201
        assert (await client.get("/api/v1/clients")).json()["items"] == []
        found = await client.get(f"/api/v1/clients/{made.json()['id']}")
        assert found.status_code == 404
        inbox = await client.post(
            "/api/v1/inboxes",
            json={"kind": "smtp", "label": "Scoped away"},
            headers={"X-CSRF-Token": csrf},
        )
        assert inbox.status_code == 201
        for path in ("/api/v1/inboxes", "/api/v1/messages", "/api/v1/results"):
            assert (await client.get(path)).json()["items"] == []
        found = await client.get(f"/api/v1/inboxes/{inbox.json()['id']}")
        assert found.status_code == 404
        status = (await client.get("/api/v1/system/status")).json()
        assert status["inboxes"] == [] and status["worker"]["heartbeat_at"] is None


def test_private_helpers_need_no_guard() -> None:
    class Fine(Repository):
        resource = "fine"

        @guarded("read")
        async def read(self, principal: Principal) -> int:
            return self._helper()

        def _helper(self) -> int:
            return 1

    assert guarded_methods(Fine) == {"read": "read"}


async def test_the_api_passes_the_signed_in_principal(
    db_engine: Any, admin: AppUser
) -> None:
    policy = RecordingPolicy()
    application = create_app(load_settings(), static_dir=None, policy=policy)
    async with running(application) as client:
        await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
        policy.calls.clear()
        assert (await client.get("/api/v1/users")).status_code == 200
    # The session lookup runs as the system; the listing as the admin.
    assert ("system", "session", "read") in policy.calls
    assert ("user", "user", "list") in policy.calls


async def test_a_refusing_policy_answers_403(db_engine: Any) -> None:
    application = create_app(load_settings(), static_dir=None, policy=DenyAllPolicy())
    async with running(application) as client:
        response: httpx.Response = await client.get("/api/v1/auth/setup-state")
    assert response.status_code == 403
    assert response.json()["title"] == "Forbidden"


def test_principals() -> None:
    user_id = uuid.uuid4()
    admin = Principal.for_user(user_id, "admin")
    assert admin.is_admin
    assert admin.actor == f"user:{user_id}"
    assert not Principal.for_user(user_id, "technician").is_admin
    token = Principal.for_token(user_id, "read")
    assert not token.is_admin
    assert token.actor == f"token:{user_id}"
    assert SYSTEM.actor == "system"
    assert as_role("admin") == "admin"
    assert as_scope("ingest") == "ingest"
    with pytest.raises(ValueError):
        as_role("owner")
    with pytest.raises(ValueError):
        as_scope("write")
