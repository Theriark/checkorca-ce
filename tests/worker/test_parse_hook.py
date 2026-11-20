"""The worker's parse hook: pending messages to results bound to their jobs.

Mail, clients and jobs are synthetic (legal R-11: example.com, fictional
companies). Messages are stored without an inbox, as the six pending rows on
Development are.
"""

import logging
import time
import uuid
import zlib
from collections.abc import AsyncIterator
from datetime import timedelta
from math import isqrt
from pathlib import Path
from typing import Any

import httpx
import pytest
import yaml
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.db.models import AppUser, Client, Job, JobResult, ParserPack, RawMessage
from app.ingest.store import ResultRejected
from app.parsers.loader import builtin_pack_texts, parse_pack
from app.repos.jobs import JobRepository
from app.repos.packs import PackRepository
from app.settings import load_settings
from app.worker import loop
from app.worker.loop import WorkerContext, build_context
from app.worker.parse import ParseHook, parse_messages
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CSRF_HEADER,
    FakeClock,
    make_client,
    make_job,
    sign_in,
)

DENTAL = "Fictional Dental Clinic"
FREIGHT = "Example Freight Ltd"
NIGHTLY = "Nightly server backup"
# Backtracks without end on a line of 1s of prime length (spike 4 of C0-B).
RUNAWAY = r"(?m)^(11+?)\1+$"


def prime_below(limit: int) -> int:
    def is_prime(number: int) -> bool:
        return all(number % divisor for divisor in range(2, isqrt(number) + 1))

    return next(number for number in range(limit, 2, -1) if is_prime(number))


ONES = "1" * prime_below(200_000)


@pytest.fixture
async def context(
    db_engine: AsyncEngine, clock: FakeClock
) -> AsyncIterator[WorkerContext]:
    built = build_context(load_settings(), clock)
    yield built
    await built.engine.dispose()


def session(engine: AsyncEngine) -> AsyncSession:
    return async_sessionmaker(engine, expire_on_commit=False)()


def mail(subject: str, body: str, sender: str = "backup@example.com") -> bytes:
    return (
        f"From: Backup Server <{sender}>\r\n"
        "To: alerts@example.net\r\n"
        f"Subject: {subject}\r\n"
        "Date: Mon, 04 Jan 2027 03:05:00 +0000\r\n"
        f"Message-ID: <{uuid.uuid4()}@example.com>\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n"
        "\r\n"
        f"Synthetic test mail.\r\n{body}\r\n"
    ).encode()


def nightly(client_hint: str = DENTAL, status: str = "Success") -> bytes:
    return mail(
        f"[{status}] {NIGHTLY}",
        f"Client: {client_hint}\r\nStatus: {status}\r\n"
        "Finished: 2027-01-04 03:01:00\r\n",
    )


async def store(
    engine: AsyncEngine, clock: FakeClock, raw: bytes, body_zlib: bytes | None = None
) -> uuid.UUID:
    """A pending message without an inbox."""
    message_id = uuid.uuid4()
    async with session(engine) as db:
        db.add(
            RawMessage(
                id=message_id,
                inbox_id=None,
                received_at=clock.now(),
                message_id=None,
                sha256="0" * 64,
                body_sha256=uuid.uuid4().hex * 2,
                size=len(raw),
                headers=[],
                body_zlib=zlib.compress(raw) if body_zlib is None else body_zlib,
                purge_after=clock.now() + timedelta(days=30),
            )
        )
        await db.commit()
    clock.advance(seconds=1)
    return message_id


async def message_of(engine: AsyncEngine, message_id: uuid.UUID) -> RawMessage:
    async with session(engine) as db:
        return (
            await db.scalars(select(RawMessage).where(RawMessage.id == message_id))
        ).one()


async def results_of(engine: AsyncEngine, message_id: uuid.UUID) -> list[JobResult]:
    async with session(engine) as db:
        query = select(JobResult).where(JobResult.raw_message_id == message_id)
        return list((await db.scalars(query)).all())


async def save_pack(engine: AsyncEngine, clock: FakeClock, **document: Any) -> None:
    """A custom pack, stored as the API stores it."""
    text = yaml.safe_dump(
        {
            "id": "example-tool",
            "version": 1,
            "vendor": "Example Tool",
            "status": "unverified-synthetic",
            "match": {"all": [{"from": r"@example\.org$"}]},
            "status_rules": [{"status": "failed", "regex": "(?i)failed"}],
        }
        | document
    )
    async with session(engine) as db:
        repository = PackRepository(db, AllowAllPolicy())
        await repository.save_custom(SYSTEM, parse_pack(text), text, clock.now())
        await db.commit()


async def tick(context: WorkerContext, clock: FakeClock, batch: int = 200) -> None:
    await ParseHook(batch)(context, clock.now())


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def test_the_hook_runs_on_every_tick() -> None:
    assert parse_messages in loop.TICK_HOOKS


async def test_a_mail_becomes_a_result_bound_to_its_job(
    client: httpx.AsyncClient,
    csrf: str,
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    job = await make_job(client, csrf, dental["id"], NIGHTLY)
    message_id = await store(db_engine, clock, nightly(client_hint="fictional dental"))
    exact = await store(db_engine, clock, nightly())
    await tick(context, clock)

    # A near miss of the client stays unmatched; the exact name binds.
    (near,) = await results_of(db_engine, message_id)
    assert near.job_id is None and near.client_hint == "fictional dental"
    (bound,) = await results_of(db_engine, exact)
    assert str(bound.job_id) == job["id"]
    assert bound.status == "success"
    assert bound.finished_at is not None and bound.finished_at.hour == 3
    stored = await message_of(db_engine, exact)
    assert stored.parse_state == "parsed"
    assert stored.parse_pack_id == "generic-keywords"
    assert stored.parsed_at == clock.now()
    assert str(stored.client_id) == dental["id"]
    assert (await message_of(db_engine, message_id)).client_id is None
    # The built-in packs were written on the way.
    packs = (await client.get("/api/v1/packs")).json()["items"]
    assert [(pack["id"], pack["source"]) for pack in packs] == [
        ("generic-keywords", "builtin")
    ]


async def test_an_unknown_failure_waits_until_create_job_binds_the_next_one(
    client: httpx.AsyncClient,
    csrf: str,
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
) -> None:
    failure = mail(
        "[Failed] Weekly archive copy",
        f"Client: {FREIGHT}\r\nStatus: Failed\r\nFinished: 2027-01-04 02:10:00\r\n",
    )
    first = await store(db_engine, clock, failure)
    await tick(context, clock)
    (result,) = await results_of(db_engine, first)
    assert result.job_id is None and result.status == "failed"
    queue = (await client.get("/api/v1/unmatched")).json()["items"]
    assert [item["result_id"] for item in queue] == [str(result.id)]
    assert queue[0]["job_name"] == "Weekly archive copy"
    assert queue[0]["client_hint"] == FREIGHT

    made = await client.post(
        f"/api/v1/unmatched/{result.id}/create-job",
        json={"client_name": FREIGHT},
        headers={CSRF_HEADER: csrf},
    )
    assert made.status_code == 201, made.text
    job = made.json()["job"]
    assert made.json()["client_created"] is True
    assert job["name"] == "Weekly archive copy"
    assert job["match_key"] == "Weekly archive copy"
    # One result: a daily schedule at its time, in the digest zone (Lisbon).
    assert (job["schedule_kind"], job["schedule_expr"]) == ("daily", "02:10")
    assert job["timezone"] == "Europe/Lisbon"
    assert (await client.get("/api/v1/unmatched")).json()["items"] == []

    # The same mail again, with a new Message-ID: bound without Unmatched.
    second = await store(db_engine, clock, failure.replace(b"02:10", b"02:12"))
    await tick(context, clock)
    (again,) = await results_of(db_engine, second)
    assert str(again.job_id) == job["id"]
    assert (await client.get("/api/v1/unmatched")).json()["items"] == []
    listed = (await client.get(f"/api/v1/jobs/{job['id']}/results")).json()["items"]
    assert [item["id"] for item in listed] == [str(again.id), str(result.id)]
    assert str((await message_of(db_engine, second)).client_id) == job["client_id"]


async def test_assign_teaches_the_matcher_the_names_of_the_mail(
    client: httpx.AsyncClient,
    csrf: str,
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    job = await make_job(client, csrf, dental["id"], "File server backup")
    # The tool calls the job and the client differently.
    first = await store(db_engine, clock, nightly(client_hint="FDC Main Office"))
    second = await store(db_engine, clock, nightly(client_hint="FDC Main Office"))
    await tick(context, clock)
    (result,) = await results_of(db_engine, first)
    assert result.job_id is None
    assigned = await client.post(
        f"/api/v1/unmatched/{result.id}/assign",
        json={"job_id": job["id"]},
        headers={CSRF_HEADER: csrf},
    )
    assert assigned.status_code == 200, assigned.text
    binding = assigned.json()
    assert binding["job_id"] == job["id"] and binding["client_id"] == dental["id"]
    assert binding["match_key_set"] is True and binding["alias_added"] is True
    # The identical mail that was already waiting is bound as well.
    assert binding["also_bound"] == 1
    (other,) = await results_of(db_engine, second)
    assert str(other.job_id) == job["id"]
    assert str((await message_of(db_engine, second)).client_id) == dental["id"]
    stored = (await client.get(f"/api/v1/jobs/{job['id']}")).json()
    assert stored["match_key"] == NIGHTLY
    aliases = (await client.get(f"/api/v1/clients/{dental['id']}")).json()["aliases"]
    assert aliases == ["FDC Main Office"]

    # The next identical mail binds at once.
    third = await store(db_engine, clock, nightly(client_hint="FDC Main Office"))
    await tick(context, clock)
    (bound,) = await results_of(db_engine, third)
    assert str(bound.job_id) == job["id"]
    # A bound result is not assigned twice.
    again = await client.post(
        f"/api/v1/unmatched/{result.id}/assign",
        json={"job_id": job["id"]},
        headers={CSRF_HEADER: csrf},
    )
    assert again.status_code == 409


async def test_unmatched_and_failed_messages_keep_their_reason(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    lunch = await store(db_engine, clock, mail("Lunch on Friday", "Noon."))
    for pack_id in ("tie-a", "tie-b"):
        await save_pack(
            db_engine, clock, id=pack_id, match={"all": [{"subject": "^Tie test$"}]}
        )
    tie = await store(db_engine, clock, mail("Tie test", "failed"))
    await save_pack(
        db_engine,
        clock,
        id="digest-tool",
        match={"all": [{"subject": "^Digest$"}]},
        split={"record": "(?m)^Job: "},
    )
    empty_digest = await store(db_engine, clock, mail("Digest", "No jobs today."))
    await tick(context, clock)

    for message_id, reason in (
        (lunch, "no-pack"),
        (tie, "tie"),
        (empty_digest, "no-records"),
    ):
        stored = await message_of(db_engine, message_id)
        assert (stored.parse_state, stored.parse_reason) == ("unmatched", reason)
        assert await results_of(db_engine, message_id) == []


async def test_a_redos_pack_fails_its_mail_and_the_tick_goes_on(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    await save_pack(
        db_engine, clock, id="runaway", match={"all": [{"body": RUNAWAY}]}
    )
    stalled = await store(db_engine, clock, mail("Report", ONES))
    later = await store(db_engine, clock, nightly())
    started = time.perf_counter()
    await tick(context, clock)
    # 50 ms for the pattern, not the hours the backtracking would take.
    assert time.perf_counter() - started < 5
    failed = await message_of(db_engine, stalled)
    assert (failed.parse_state, failed.parse_reason) == ("error", "timeout")
    assert (failed.parse_pack_id, failed.parse_path) == ("runaway", "/match/all/0/body")
    assert (await message_of(db_engine, later)).parse_state == "parsed"


async def test_a_message_that_cannot_be_parsed_never_stops_the_tick(
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    broken = await store(db_engine, clock, b"", body_zlib=b"not zlib")
    huge = await store(
        db_engine, clock, b"", body_zlib=zlib.compress(b"x" * (5 * 1024 * 1024 + 1))
    )
    good = await store(db_engine, clock, nightly())
    with caplog.at_level(logging.WARNING, logger="app.worker.parse"):
        await tick(context, clock)
    assert (await message_of(db_engine, broken)).parse_reason == "internal"
    assert (await message_of(db_engine, huge)).parse_reason == "unreadable"
    assert (await message_of(db_engine, good)).parse_state == "parsed"
    assert "left unparsed" in caplog.text
    # Nothing of the mail reaches the log.
    assert "Synthetic test mail" not in caplog.text

    async def refuse(*args: object, **kwargs: object) -> None:
        raise ResultRejected("details must be an object")

    monkeypatch.setattr("app.worker.parse.record_result", refuse)
    refused = await store(db_engine, clock, nightly())
    await tick(context, clock)
    stored = await message_of(db_engine, refused)
    assert (stored.parse_state, stored.parse_reason) == ("error", "rejected")
    assert await results_of(db_engine, refused) == []


async def test_a_locked_message_is_skipped_and_a_tick_parses_a_batch(
    context: WorkerContext, db_engine: AsyncEngine, clock: FakeClock
) -> None:
    held = await store(db_engine, clock, nightly())
    first = await store(db_engine, clock, nightly())
    second = await store(db_engine, clock, nightly())
    async with session(db_engine) as other:
        await other.execute(
            select(RawMessage.id).where(RawMessage.id == held).with_for_update()
        )
        await tick(context, clock, batch=1)
        assert (await message_of(db_engine, held)).parse_state == "pending"
        assert (await message_of(db_engine, first)).parse_state == "parsed"
        assert (await message_of(db_engine, second)).parse_state == "pending"
        await other.rollback()
    await tick(context, clock)
    for message_id in (held, second):
        assert (await message_of(db_engine, message_id)).parse_state == "parsed"


async def test_disabled_and_broken_packs_parse_nothing(
    context: WorkerContext,
    db_engine: AsyncEngine,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    await tick(context, clock)
    async with session(db_engine) as db:
        await db.execute(update(ParserPack).values(enabled=False))
        db.add(
            ParserPack(
                id="broken-tool",
                version=1,
                vendor="Example Tool",
                status="unverified-synthetic",
                source="custom",
                yaml="id: [",
                enabled=True,
                created_at=clock.now(),
                updated_at=clock.now(),
            )
        )
        await db.commit()
    message_id = await store(db_engine, clock, nightly())
    with caplog.at_level(logging.ERROR, logger="app.worker.parse"):
        await tick(context, clock)
    stored = await message_of(db_engine, message_id)
    assert (stored.parse_state, stored.parse_reason) == ("unmatched", "no-pack")
    assert "broken-tool does not load" in caplog.text


def write_pack(folder: Path, pack_id: str, version: int = 1) -> None:
    document = {
        "id": pack_id,
        "version": version,
        "vendor": "Example Tool",
        "status": "unverified-synthetic",
        "match": {"all": [{"from": r"@example\.com$"}]},
        "status_rules": [{"status": "success", "regex": "(?i)success"}],
    }
    (folder / f"{pack_id}.yaml").write_text(yaml.safe_dump(document), "utf-8")


async def rows(engine: AsyncEngine) -> dict[str, tuple[int, str, bool]]:
    async with session(engine) as db:
        found = (await db.scalars(select(ParserPack))).all()
    return {pack.id: (pack.version, pack.source, pack.enabled) for pack in found}


async def sync(engine: AsyncEngine, clock: FakeClock, folder: Path) -> None:
    async with session(engine) as db:
        repository = PackRepository(db, AllowAllPolicy())
        await repository.sync_builtin(SYSTEM, builtin_pack_texts(folder), clock.now())
        await db.commit()


async def test_the_built_in_packs_are_synced_and_keep_the_users_choice(
    db_engine: AsyncEngine, clock: FakeClock, tmp_path: Path
) -> None:
    write_pack(tmp_path, "alpha-tool")
    write_pack(tmp_path, "beta-tool")
    await save_pack(db_engine, clock, id="gamma-tool")
    await sync(db_engine, clock, tmp_path)
    assert await rows(db_engine) == {
        "alpha-tool": (1, "builtin", True),
        "beta-tool": (1, "builtin", True),
        "gamma-tool": (1, "custom", True),
    }
    async with session(db_engine) as db:
        alpha = ParserPack.id == "alpha-tool"
        await db.execute(update(ParserPack).where(alpha).values(enabled=False))
        await db.commit()
    # A new release: alpha changes, beta is gone, gamma ships as built-in.
    write_pack(tmp_path, "alpha-tool", version=2)
    (tmp_path / "beta-tool.yaml").unlink()
    write_pack(tmp_path, "gamma-tool", version=5)
    await sync(db_engine, clock, tmp_path)
    assert await rows(db_engine) == {
        "alpha-tool": (2, "builtin", False),
        "gamma-tool": (1, "custom", True),
    }
    # Unchanged packs are not written again.
    clock.advance(hours=1)
    await sync(db_engine, clock, tmp_path)
    async with session(db_engine) as db:
        alpha = await db.get(ParserPack, "alpha-tool")
    assert alpha is not None and alpha.updated_at == clock.now() - timedelta(hours=1)


async def test_the_matcher_leaves_out_archived_jobs_and_clients(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    freight = await make_client(client, csrf, FREIGHT)
    kept = await make_job(client, csrf, dental["id"], NIGHTLY)
    archived = await make_job(client, csrf, dental["id"], "Old backup")
    await make_job(client, csrf, freight["id"], NIGHTLY)
    async with session(db_engine) as db:
        await db.execute(
            update(Job).where(Job.id == uuid.UUID(archived["id"])).values(archived=True)
        )
        await db.execute(
            update(Client)
            .where(Client.id == uuid.UUID(freight["id"]))
            .values(archived=True)
        )
        await db.commit()
        matcher = await JobRepository(db, AllowAllPolicy()).matcher(SYSTEM)
    # Freight's job is archived with its client: the name is not ambiguous.
    found = matcher.match(NIGHTLY, None)
    assert str(getattr(found, "job_id", None)) == kept["id"]
    assert getattr(matcher.match("Old backup", DENTAL), "reason", None) == "no-job"
