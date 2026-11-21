"""packs: list, read, save, import, export, enable, disable, and packs/test.

Packs and mail are synthetic (legal R-11: example.com, fictional companies).
packs/test runs in a real child process here.
"""

import asyncio
import base64
import json
import subprocess
import sys
import time
import warnings
from typing import Any

import httpx
import pytest
import yaml
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from app.access import SYSTEM, AllowAllPolicy
from app.api.bench import (
    COMMAND,
    ROOT,
    BenchRunner,
    BenchUnavailable,
    child_environment,
)
from app.api.v1.pack_schemas import MAX_TEST_MAIL
from app.db.models import AppUser, AuditEvent
from app.main import create_app
from app.parsers.loader import PACKS_DIR, builtin_pack_texts
from app.repos.packs import PackRepository
from app.settings import load_settings
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CSRF_HEADER,
    TECHNICIAN_EMAIL,
    TECHNICIAN_PASSWORD,
    FakeClock,
    running,
    sign_in,
)

GENERIC = (PACKS_DIR / "generic-keywords.yaml").read_text("utf-8")
RAW = (
    "From: Backup Server <backup@example.com>\r\n"
    "To: alerts@example.net\r\n"
    "Subject: [Failed] Nightly server backup\r\n"
    "Date: Mon, 04 Jan 2027 03:05:00 +0000\r\n"
    "\r\n"
    "Client: Fictional Dental Clinic\r\n"
    "Status: Failed\r\n"
)
RUNAWAY = r"(?m)^(11+?)\1+$"
# 199,999 is prime: the pattern backtracks without end on this line.
ONES = "1" * 199_999


def pack_text(pack_id: str = "example-tool", version: int = 1, **changes: Any) -> str:
    document = {
        "id": pack_id,
        "version": version,
        "vendor": "Example Tool",
        "status": "unverified-synthetic",
        "match": {"all": [{"from": r"@example\.com"}, {"subject": "Nightly"}]},
        "status_rules": [{"status": "failed", "regex": "(?i)status: failed"}],
    }
    document.update(changes)
    return yaml.safe_dump(document)


@pytest.fixture
async def synced(db_engine: AsyncEngine, clock: FakeClock) -> None:
    """The built-in packs, as the start of the app writes them."""
    async with async_sessionmaker(db_engine)() as db:
        repository = PackRepository(db, AllowAllPolicy())
        await repository.sync_builtin(SYSTEM, builtin_pack_texts(), clock.now())
        await db.commit()


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser, synced: None) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def put(client: httpx.AsyncClient, csrf: str, pack_id: str, body: str) -> Any:
    return await client.put(
        f"/api/v1/packs/{pack_id}", json={"yaml": body}, headers={CSRF_HEADER: csrf}
    )


async def test_the_built_in_pack_is_listed_and_read(
    client: httpx.AsyncClient, csrf: str
) -> None:
    listed = await client.get("/api/v1/packs")
    assert listed.status_code == 200
    (item,) = listed.json()["items"]
    assert (item["id"], item["source"], item["enabled"]) == (
        "generic-keywords",
        "builtin",
        True,
    )
    assert item["status"] == "unverified-synthetic" and "yaml" not in item
    detail = await client.get("/api/v1/packs/generic-keywords")
    assert detail.json()["yaml"] == GENERIC
    assert (await client.get("/api/v1/packs/no-such-pack")).status_code == 404
    assert (await client.get("/api/v1/packs/Not_An_Id")).status_code == 422


async def test_packs_are_paged_by_id(client: httpx.AsyncClient, csrf: str) -> None:
    for pack_id in ("alpha-tool", "beta-tool"):
        saved = await put(client, csrf, pack_id, pack_text(pack_id))
        assert saved.status_code == 201
    first = (await client.get("/api/v1/packs", params={"limit": 2})).json()
    assert [item["id"] for item in first["items"]] == ["alpha-tool", "beta-tool"]
    rest = await client.get(
        "/api/v1/packs", params={"limit": 2, "cursor": first["next_cursor"]}
    )
    assert [item["id"] for item in rest.json()["items"]] == ["generic-keywords"]
    assert rest.json()["next_cursor"] is None
    bad = await client.get("/api/v1/packs", params={"cursor": "not-a-cursor"})
    assert bad.status_code == 400


async def test_a_custom_pack_is_saved_and_must_raise_its_version(
    client: httpx.AsyncClient, csrf: str, db_engine: AsyncEngine
) -> None:
    created = await put(client, csrf, "example-tool", pack_text())
    assert created.status_code == 201, created.text
    assert created.json()["source"] == "custom" and created.json()["version"] == 1
    # The same text again changes nothing.
    assert (await put(client, csrf, "example-tool", pack_text())).status_code == 200
    changed = pack_text(vendor="Example Tool 2")
    same_version = await put(client, csrf, "example-tool", changed)
    assert same_version.status_code == 422
    assert same_version.json()["issues"] == [
        {"path": "/version", "message": "must be higher than 1, the saved version"}
    ]
    raised = await put(
        client, csrf, "example-tool", pack_text(version=2, vendor="Example Tool 2")
    )
    assert raised.status_code == 200 and raised.json()["vendor"] == "Example Tool 2"
    async with db_engine.connect() as connection:
        actions = await connection.execute(
            select(AuditEvent.action, AuditEvent.target_id).order_by(AuditEvent.at)
        )
        saved = [row for row in actions.all() if row.action == "pack.save"]
    assert [row.target_id for row in saved] == ["example-tool", "example-tool"]


@pytest.mark.parametrize(
    ("body", "path"),
    [
        (pack_text("other-tool"), "/id"),
        (pack_text(status_rules=[]), "/status_rules"),
        (
            pack_text(status_rules=[{"status": "failed", "regex": "("}]),
            "/status_rules/0/regex",
        ),
        ("id: [", ""),
        ("a: &x [1]\nb: *x\n", ""),
    ],
)
async def test_a_pack_that_does_not_load_answers_its_issues(
    client: httpx.AsyncClient, csrf: str, body: str, path: str
) -> None:
    response = await put(client, csrf, "example-tool", body)
    assert response.status_code == 422
    problem = response.json()
    assert problem["title"] == "Invalid parser pack"
    assert path in [issue["path"] for issue in problem["issues"]]
    assert all(issue["message"] for issue in problem["issues"])


async def test_the_second_of_two_new_saves_of_an_id_gets_409(
    client: httpx.AsyncClient, csrf: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = await put(client, csrf, "example-tool", pack_text())
    assert first.status_code == 201
    get = PackRepository.get

    async def not_yet_saved(*args: Any, **kwargs: Any) -> Any:
        # The second request looked before the first one committed.
        return None

    monkeypatch.setattr(PackRepository, "get", not_yet_saved)
    second = await put(client, csrf, "example-tool", pack_text(vendor="Other"))
    assert second.status_code == 409
    assert second.json()["title"] == "Parser pack changed meanwhile"
    monkeypatch.setattr(PackRepository, "get", get)
    stored = await client.get("/api/v1/packs/example-tool")
    assert stored.json()["vendor"] == "Example Tool"


async def test_a_built_in_pack_cannot_be_changed(
    client: httpx.AsyncClient, csrf: str
) -> None:
    copy = GENERIC.replace("version: 3", "version: 4")
    response = await put(client, csrf, "generic-keywords", copy)
    assert response.status_code == 409
    stored = await client.get("/api/v1/packs/generic-keywords")
    assert stored.json()["yaml"] == GENERIC


async def test_a_pack_is_exported_and_imported(
    client: httpx.AsyncClient, csrf: str
) -> None:
    exported = await client.get("/api/v1/packs/generic-keywords/export")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/yaml")
    assert 'filename="generic-keywords.yaml"' in exported.headers["content-disposition"]
    assert exported.text == GENERIC
    assert (await client.get("/api/v1/packs/none/export")).status_code == 404

    async def upload(data: bytes) -> httpx.Response:
        return await client.post(
            "/api/v1/packs/import",
            files={"file": ("pack.yaml", data, "application/yaml")},
            headers={CSRF_HEADER: csrf},
        )

    imported = await upload(pack_text("other-tool").encode())
    assert imported.status_code == 201 and imported.json()["id"] == "other-tool"
    assert (await upload(pack_text("other-tool").encode())).status_code == 200
    assert (await upload(GENERIC.encode())).status_code == 409
    too_large = await upload(b"#" * (64 * 1024 + 1))
    assert too_large.status_code == 422
    assert too_large.json()["issues"][0]["path"] == ""
    not_text = await upload(b"\xff\xfe id: x")
    assert not_text.status_code == 422


async def test_any_pack_is_disabled_and_enabled(
    client: httpx.AsyncClient, csrf: str
) -> None:
    for action, enabled in (("disable", False), ("disable", False), ("enable", True)):
        response = await client.post(
            f"/api/v1/packs/generic-keywords/{action}", headers={CSRF_HEADER: csrf}
        )
        assert response.status_code == 200 and response.json()["enabled"] is enabled
    unknown = await client.post(
        "/api/v1/packs/none/enable", headers={CSRF_HEADER: csrf}
    )
    assert unknown.status_code == 404


async def test_a_technician_uses_the_pack_routes(
    client: httpx.AsyncClient, technician: AppUser, synced: None
) -> None:
    csrf = await sign_in(client, TECHNICIAN_EMAIL, TECHNICIAN_PASSWORD)
    assert (await put(client, csrf, "example-tool", pack_text())).status_code == 201
    tested = await client.post(
        "/api/v1/packs/test", json={"raw": RAW}, headers={CSRF_HEADER: csrf}
    )
    assert tested.status_code == 200, tested.text


async def bench_test(
    client: httpx.AsyncClient, csrf: str, **body: Any
) -> httpx.Response:
    return await client.post(
        "/api/v1/packs/test", json=body, headers={CSRF_HEADER: csrf}
    )


async def test_the_bench_shows_the_claim_the_scores_and_the_spans(
    client: httpx.AsyncClient, csrf: str
) -> None:
    response = await bench_test(client, csrf, raw=RAW)
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["claimed_by"] == "generic-keywords"
    assert answer["scores"] == [{"pack_id": "generic-keywords", "matched": 1}]
    assert (answer["outcome"], answer["pack_id"]) == ("parsed", "generic-keywords")
    (result,) = answer["results"]
    assert (result["job_name"], result["status"]) == ("Nightly server backup", "failed")
    spans = {span["field"]: span for span in result["spans"]}
    name = spans["job_name"]
    assert name["source"] == "subject"
    subject = answer["mail"]["subject"]
    assert subject[name["start"] : name["end"]] == "Nightly server backup"
    hint = spans["client_hint"]
    body = answer["mail"]["body"]
    assert body[hint["start"] : hint["end"]] == "Fictional Dental Clinic"


async def test_the_bench_runs_the_pack_being_edited(
    client: httpx.AsyncClient, csrf: str
) -> None:
    response = await bench_test(client, csrf, raw=RAW, pack=pack_text())
    answer = response.json()
    assert answer["scores"] == [
        {"pack_id": "example-tool", "matched": 2},
        {"pack_id": "generic-keywords", "matched": 1},
    ]
    assert answer["claimed_by"] == "example-tool"
    assert answer["results"][0]["status"] == "failed"
    # A disabled pack is not tried.
    disable = "/api/v1/packs/generic-keywords/disable"
    await client.post(disable, headers={CSRF_HEADER: csrf})
    alone = (await bench_test(client, csrf, raw=RAW)).json()
    assert alone["scores"] == [] and alone["reason"] == "no-pack"


async def test_the_bench_refuses_a_pack_that_does_not_load_or_is_too_large(
    client: httpx.AsyncClient, csrf: str
) -> None:
    invalid = await bench_test(client, csrf, raw=RAW, pack="id: [")
    assert invalid.status_code == 422 and invalid.json()["issues"]
    over_cap = await bench_test(client, csrf, raw=RAW, pack="#" * (64 * 1024 + 1))
    assert over_cap.status_code == 422
    # Two bytes a character: under the character limit, over the byte cap.
    wide = await bench_test(client, csrf, raw=RAW, pack="é" * (40 * 1024))
    assert wide.status_code == 422
    assert wide.json()["issues"][0]["message"].startswith("a pack may have at most")
    missing = await bench_test(client, csrf, pack=pack_text())
    assert missing.status_code == 422
    assert missing.json()["errors"][0]["field"] == "body.raw"
    not_json = await client.post(
        "/api/v1/packs/test", content=b"{", headers={CSRF_HEADER: csrf}
    )
    assert not_json.status_code == 422


async def test_the_bench_caps_its_body_and_the_mail(
    client: httpx.AsyncClient, csrf: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    wide_mail = await bench_test(client, csrf, raw="é" * (600 * 1024))
    assert wide_mail.status_code == 413
    monkeypatch.setattr("app.api.v1.packs.MAX_TEST_BODY", 64)
    declared = await bench_test(client, csrf, raw=RAW)
    assert declared.status_code == 413

    async def chunks() -> Any:
        for _ in range(10):
            yield b'{"raw": "' + b"x" * 10

    streamed = await client.post(
        "/api/v1/packs/test", content=chunks(), headers={CSRF_HEADER: csrf}
    )
    assert streamed.status_code == 413


async def test_the_bench_has_its_own_rate_limit(
    client: httpx.AsyncClient, csrf: str
) -> None:
    for _ in range(30):
        assert (await bench_test(client, csrf)).status_code == 422
    limited = await bench_test(client, csrf, raw=RAW)
    assert limited.status_code == 429 and "retry-after" in limited.headers


async def test_a_redos_pack_stalls_neither_the_bench_nor_the_web_process(
    client: httpx.AsyncClient, csrf: str
) -> None:
    runaway = pack_text(status_rules=[{"status": "failed", "regex": RUNAWAY}])
    raw = RAW + ONES + "\r\n"
    started = time.perf_counter()
    tested = asyncio.create_task(bench_test(client, csrf, raw=raw, pack=runaway))
    # The web process answers while the child matches.
    health = await client.get("/healthz")
    assert health.status_code == 200
    assert time.perf_counter() - started < 1.0
    response = await tested
    assert time.perf_counter() - started < 15
    answer = response.json()
    assert (answer["outcome"], answer["reason"]) == ("error", "timeout")
    assert answer["path"] == "/status_rules/0/regex"


async def test_a_slow_custom_pack_is_skipped_and_generic_keywords_claims(
    client: httpx.AsyncClient, csrf: str
) -> None:
    slow = pack_text("slow-tool", match={"all": [{"body": RUNAWAY}]})
    assert (await put(client, csrf, "slow-tool", slow)).status_code == 201
    response = await bench_test(client, csrf, raw=RAW + ONES + "\r\n")
    assert response.status_code == 200, response.text
    answer = response.json()
    assert answer["claimed_by"] == "generic-keywords"
    assert (answer["outcome"], answer["pack_id"]) == ("parsed", "generic-keywords")
    assert answer["results"][0]["status"] == "failed"
    assert answer["skipped"] == [
        {"pack_id": "slow-tool", "reason": "timeout", "path": "/match/all/0/body"}
    ]


async def test_the_bench_never_runs_the_engine_in_this_process(
    client: httpx.AsyncClient, csrf: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("the engine ran in the web process")

    for name in ("bench", "parse", "apply"):
        monkeypatch.setattr(f"app.parsers.engine.{name}", refuse)
    monkeypatch.setattr("app.parsers.bench.bench", refuse)
    monkeypatch.setattr("app.worker.parse.on_parser_thread", refuse)
    response = await bench_test(client, csrf, raw=RAW)
    assert response.status_code == 200
    assert response.json()["claimed_by"] == "generic-keywords"


@pytest.mark.parametrize(
    ("command", "timeout"),
    [
        ([sys.executable, "-c", "import time; time.sleep(30)"], 0.5),
        ([sys.executable, "-c", "import sys; sys.exit(3)"], 10.0),
        ([sys.executable, "-c", "print('not json')"], 10.0),
    ],
)
async def test_a_child_that_does_not_answer_gives_503(
    db_engine: AsyncEngine,
    admin: AppUser,
    synced: None,
    clock: FakeClock,
    command: list[str],
    timeout: float,
) -> None:
    runner = BenchRunner(command=command, timeout=timeout)
    app: FastAPI = create_app(
        load_settings(), static_dir=None, clock=clock, bench=runner
    )
    async with running(app) as client:
        csrf = await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
        started = time.perf_counter()
        response = await bench_test(client, csrf, raw=RAW)
    assert response.status_code == 503
    assert response.json()["title"] == "Test bench unavailable"
    assert time.perf_counter() - started < timeout + 5


async def test_a_full_bench_is_busy_and_a_cancelled_test_kills_its_child(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started: list[asyncio.subprocess.Process] = []
    start = asyncio.create_subprocess_exec

    async def recorded(*args: Any, **kwargs: Any) -> asyncio.subprocess.Process:
        child = await start(*args, **kwargs)
        started.append(child)
        return child

    monkeypatch.setattr(asyncio, "create_subprocess_exec", recorded)
    sleeper = [sys.executable, "-c", "import time; time.sleep(30)"]
    runner = BenchRunner(command=sleeper, timeout=30, max_running=1, slot_wait=0.2)
    first = asyncio.create_task(runner.run([], None, b"x"))
    while not started:
        await asyncio.sleep(0.02)
    waited = time.perf_counter()
    with pytest.raises(BenchUnavailable, match="busy"):
        await runner.run([], None, b"x")
    assert time.perf_counter() - waited < 2
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    # The child is gone, not left to run out its 30 s; only one ever started.
    assert len(started) == 1 and started[0].returncode is not None


# The real child, its memory limit just above what it uses once its modules
# are loaded: the request does not fit.
TIGHT_CHILD = """
import sys
from app.parsers import bench
status = open("/proc/self/status").read().split()
size = int(status[status.index("VmSize:") + 1]) * 1024
bench.MEMORY_BYTES = size + 256 * 1024
sys.exit(bench.main())
"""
# About 900 KB of text in lines, under the 1 MiB the route takes.
LONG_BODY = ("Line of a long synthetic job report.\r\n" * 24_000)[: 900 * 1024]


async def test_a_child_over_its_memory_limit_answers_memory_and_the_web_serves(
    db_engine: AsyncEngine, admin: AppUser, synced: None, clock: FakeClock
) -> None:
    runner = BenchRunner(command=[sys.executable, "-c", TIGHT_CHILD])
    app: FastAPI = create_app(
        load_settings(), static_dir=None, clock=clock, bench=runner
    )
    async with running(app) as client:
        csrf = await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)
        response = await bench_test(client, csrf, raw=RAW + LONG_BODY)
        assert response.status_code == 200, response.text
        answer = response.json()
        assert (answer["outcome"], answer["reason"]) == ("error", "memory")
        assert answer["results"] == []
        # The web process keeps serving, the next test included.
        assert (await client.get("/healthz")).status_code == 200
        runner.command = COMMAND
        again = await bench_test(client, csrf, raw=RAW)
        assert again.json()["claimed_by"] == "generic-keywords"


# The real child, reporting what it used (C5-B2 measurement, temporary).
MEASURED_CHILD = """
import sys
def show(label):
    status = open("/proc/self/status").read().splitlines()
    kept = [x for x in status if x.startswith(("VmPeak", "VmHWM"))]
    print(label, " ".join(kept), file=sys.stderr)
from app.parsers import bench
show("loaded")
try:
    sys.exit(bench.main())
finally:
    show("done")
"""
# The app's modules and one Argon2 hash (C5-B2 measurement, temporary).
MEASURED_WEB = """
import base64
from argon2 import PasswordHasher
import app.ingest.imap, app.ingest.smtp, app.worker.loop
from app.main import create_app
from app.settings import load_settings
def show(label):
    status = open("/proc/self/status").read().splitlines()
    keep = ("VmPeak", "VmSize", "VmHWM", "VmRSS")
    print(label, " ".join(x for x in status if x.startswith(keep)))
key = base64.urlsafe_b64encode(bytes(32)).decode()
url = "postgresql+asyncpg://unused@127.0.0.1:1/unused"
settings = load_settings(secret_key="m" * 40, fernet_key=key, database_url=url)
create_app(settings, static_dir=None).openapi()
show("app")
PasswordHasher().hash("x" * 20)
show("argon2")
"""


def test_the_largest_test_fits_the_memory_limit_of_the_child() -> None:
    """The real child at its real limits with the largest request the route
    lets through: a 1 MiB mail, an edited pack of 50 long rules and the
    built-in pack."""
    rules = [{"status": "warning", "regex": "z" * 1000} for _ in range(49)]
    rules.append({"status": "failed", "regex": "(?i)status: failed"})
    raw = (RAW + LONG_BODY + "x" * (100 * 1024)).encode()[:MAX_TEST_MAIL]
    request = {
        "packs": [["generic-keywords", GENERIC]],
        "pack": pack_text(status_rules=rules),
        "raw": base64.b64encode(raw).decode(),
    }
    child = subprocess.run(
        [sys.executable, "-c", MEASURED_CHILD],
        input=json.dumps(request).encode(),
        capture_output=True,
        cwd=ROOT,
        env=child_environment(),
        timeout=60,
        check=False,
    )
    warnings.warn(f"bench child: {child.stderr.decode()[-300:]}", stacklevel=1)
    assert child.returncode == 0, child.stderr
    answer = json.loads(child.stdout)
    assert (answer["outcome"], answer["reason"]) == ("parsed", None)
    assert answer["results"][0]["status"] == "failed"


def test_measure_the_web_process() -> None:
    """Temporary (C5-B2 measurement): memory of the app's modules."""
    child = subprocess.run(
        [sys.executable, "-c", MEASURED_WEB],
        capture_output=True,
        cwd=ROOT,
        timeout=60,
        check=False,
    )
    output = f"{child.stdout.decode()} {child.stderr.decode()[-300:]}"
    warnings.warn(f"web: {output}", stacklevel=1)


def test_the_child_gets_no_setting_of_the_web_process() -> None:
    environment = child_environment()
    assert set(environment) <= {"PATH", "LANG", "PYTHONDONTWRITEBYTECODE"}
    assert "SECRET_KEY" not in environment and "DATABASE_URL" not in environment
