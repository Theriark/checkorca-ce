"""python -m app: the commands and the ROLE default."""

import asyncio
import logging

import pytest
import uvicorn
from alembic.script import ScriptDirectory
from sqlalchemy import text

import app.__main__ as cli
from app.db.engine import make_engine
from app.settings import Settings, load_settings

pytestmark = pytest.mark.usefixtures("quiet_cli")


async def current_revision() -> str:
    engine = make_engine(load_settings().database_url.get_secret_value())
    query = text("SELECT version_num FROM alembic_version")
    try:
        async with engine.connect() as connection:
            return str((await connection.execute(query)).scalar_one())
    finally:
        await engine.dispose()


def test_invalid_settings_exit_with_2(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("SECRET_KEY")
    assert cli.main(["web"]) == 2
    assert "SECRET_KEY" in capsys.readouterr().err


def test_unknown_command_is_refused() -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["deploy"])
    assert caught.value.code == 2


def test_migrate_upgrades_the_database_to_head() -> None:
    scripts = ScriptDirectory.from_config(cli.alembic_config(load_settings()))
    assert cli.main(["migrate"]) == 0
    assert asyncio.run(current_revision()) == scripts.get_current_head() == "c9_notify"
    # A second run finds nothing to do.
    assert cli.main(["migrate"]) == 0


def test_seed_without_dev_seed_does_nothing(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app"):
        assert cli.main(["seed"]) == 0
    assert "nothing to seed" in caplog.text


@pytest.mark.parametrize(("argv", "role"), [(["worker"], "all"), ([], "worker")])
def test_worker_runs_the_worker_loop(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], role: str
) -> None:
    monkeypatch.setenv("ROLE", role)
    calls: list[asyncio.Event] = []

    async def fake_run_worker(settings: Settings, stop: asyncio.Event) -> None:
        calls.append(stop)

    monkeypatch.setattr(cli, "run_worker", fake_run_worker)
    assert cli.main(argv) == 0
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("argv", "role", "with_worker"),
    [
        (["web"], "all", False),
        (["all"], "web", True),
        ([], "all", True),
        ([], "web", False),
    ],
)
def test_web_and_all_migrate_before_serving(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], role: str, with_worker: bool
) -> None:
    monkeypatch.setenv("ROLE", role)
    events: list[object] = []

    def fake_migrate(settings: Settings) -> None:
        events.append("migrate")

    def fake_seed(settings: Settings) -> None:
        events.append("seed")

    async def fake_serve(settings: Settings, with_worker: bool) -> None:
        events.append(("serve", with_worker))

    monkeypatch.setattr(cli, "migrate", fake_migrate)
    monkeypatch.setattr(cli, "seed", fake_seed)
    monkeypatch.setattr(cli, "serve", fake_serve)
    assert cli.main(argv) == 0
    # The seed accounts exist before the HTTP port opens (first-run takeover).
    assert events == ["migrate", "seed", ("serve", with_worker)]


async def test_serve_starts_and_stops_the_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ports: list[int] = []

    async def fake_serve(self: uvicorn.Server, sockets: object = None) -> None:
        ports.append(self.config.port)

    monkeypatch.setattr(uvicorn.Server, "serve", fake_serve)
    settings = load_settings(port=18080)
    await cli.serve(settings, with_worker=True)
    await cli.serve(settings, with_worker=False)
    assert ports == [18080, 18080]


async def test_rotate_fernet_re_encrypts_and_prints_only_counts(
    db_engine, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command moves the stored secrets to the new key and says only how
    many; no key or secret value reaches the output."""
    import base64
    from datetime import UTC, datetime

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.access import AllowAllPolicy, SYSTEM
    from app.db.models import Channel, Inbox
    from app.repos.inboxes import InboxRepository
    from app.repos.notifications import ChannelRepository
    from app.security.crypto import SecretBox
    from helpers import TEST_FERNET_KEY

    old = SecretBox(TEST_FERNET_KEY)
    new_key = base64.urlsafe_b64encode(b"\x05" * 32).decode()
    secret = "relay-password-cli-test"
    now = datetime(2027, 1, 4, 9, tzinfo=UTC)
    policy = AllowAllPolicy()
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        await InboxRepository(db, policy).create(
            SYSTEM,
            kind="imap",
            label="Vendor mailbox",
            now=now,
            imap_host="imap.example.com",
            imap_password_enc=old.encrypt(secret),
        )
        await ChannelRepository(db, policy).create(
            SYSTEM, kind="email", label="Ops mail", now=now, config={}
        )
        await db.commit()
    monkeypatch.setenv("FERNET_KEY", f"{new_key},{TEST_FERNET_KEY}")
    assert cli.main(["rotate-fernet"]) == 0
    out = capsys.readouterr().out
    assert "rotated 1 stored credential(s)" in out
    assert secret not in out
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        inbox = (await db.scalars(select(Inbox))).one()
        assert SecretBox(new_key).decrypt(inbox.imap_password_enc) == secret
        channel = (await db.scalars(select(Channel))).one()
        assert channel.secret_enc is None


async def test_rotate_fernet_refuses_without_the_old_key(
    db_engine,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A row the new key cannot read refuses the whole command: exit 2, a
    readable message, nothing changed."""
    import base64
    from datetime import UTC, datetime

    from sqlalchemy.ext.asyncio import async_sessionmaker

    from app.access import AllowAllPolicy, SYSTEM
    from app.repos.inboxes import InboxRepository
    from app.security.crypto import SecretBox
    from helpers import TEST_FERNET_KEY

    old = SecretBox(TEST_FERNET_KEY)
    new_key = base64.urlsafe_b64encode(b"\x06" * 32).decode()
    now = datetime(2027, 1, 4, 9, tzinfo=UTC)
    policy = AllowAllPolicy()
    async with async_sessionmaker(db_engine, expire_on_commit=False)() as db:
        await InboxRepository(db, policy).create(
            SYSTEM,
            kind="imap",
            label="Vendor mailbox",
            now=now,
            imap_host="imap.example.com",
            imap_password_enc=old.encrypt("relay-password-cli-refused"),
        )
        await db.commit()
    monkeypatch.setenv("FERNET_KEY", new_key)
    assert cli.main(["rotate-fernet"]) == 2
    err = capsys.readouterr().err
    assert "cannot be decrypted" in err
    assert "relay-password-cli-refused" not in err
