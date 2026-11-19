"""Jobs CSV: export with the formula guard, import with row errors, round trip."""

import codecs
import csv
import io
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1.jobs_csv import COLUMNS, guard_cell, unguard_cell
from app.db.models import AppUser
from helpers import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    CLIENT_NAMES,
    CSRF_HEADER,
    another_browser,
    make_client,
    make_job,
    sign_in,
)

DENTAL, FREIGHT, LAW = CLIENT_NAMES
HEADER = ",".join(COLUMNS)
BOM = codecs.BOM_UTF8.decode("utf-8")


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


def read_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text.removeprefix(BOM))))


async def export(client: httpx.AsyncClient, **params: str) -> httpx.Response:
    response = await client.get("/api/v1/jobs/export.csv", params=params)
    assert response.status_code == 200, response.text
    return response


async def upload(
    client: httpx.AsyncClient, csrf: str, content: str | bytes, **params: str
) -> httpx.Response:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return await client.post(
        "/api/v1/jobs/import.csv",
        params=params,
        files={"file": ("jobs.csv", data, "text/csv")},
        headers={CSRF_HEADER: csrf},
    )


@pytest.mark.parametrize(
    ("value", "guarded"),
    [
        ("=HYPERLINK(1)", "'=HYPERLINK(1)"),
        ("+1", "'+1"),
        ("-1", "'-1"),
        ("@daily", "'@daily"),
        ("\tTab", "'\tTab"),
        ("\rReturn", "'\rReturn"),
        ("'=quoted", "''=quoted"),
        ("'plain", "'plain"),
        ("Plain", "Plain"),
        ("", ""),
    ],
)
def test_the_formula_guard_round_trips(value: str, guarded: str) -> None:
    assert guard_cell(value) == guarded
    assert unguard_cell(guarded) == value


async def test_export_lists_jobs_with_guarded_cells(
    client: httpx.AsyncClient, csrf: str
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    hostile = await make_client(client, csrf, "=cmd Fictional Co")
    await make_job(client, csrf, dental["id"], "Nightly server backup")
    await make_job(
        client,
        csrf,
        hostile["id"],
        "@SUM(1+1) report",
        kind="script",
        schedule_kind="cron",
        schedule_expr="@daily",
        timezone="UTC",
        match_key="-report",
    )
    archived = await make_job(client, csrf, dental["id"], "Archived backup")
    await client.post(
        f"/api/v1/jobs/{archived['id']}/archive", headers={CSRF_HEADER: csrf}
    )
    response = await export(client)
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert "attachment" in response.headers["content-disposition"]
    assert response.text.startswith(BOM + HEADER + "\r\n")
    rows = sorted(read_csv(response.text), key=lambda row: row["client"])
    assert [row["client"] for row in rows] == ["'=cmd Fictional Co", DENTAL]
    hostile_row = rows[0]
    assert hostile_row["job"] == "'@SUM(1+1) report"
    assert hostile_row["schedule_expr"] == "0 0 * * *"
    assert hostile_row["match_key"] == "'-report"
    assert rows[1] == {
        "client": DENTAL,
        "job": "Nightly server backup",
        "kind": "backup",
        "schedule_kind": "daily",
        "schedule_expr": "23:00",
        "timezone": "Europe/Lisbon",
        "max_runtime_minutes": "360",
        "grace_minutes": "120",
        "escalate_minutes": "30",
        "warning_policy": "warning_is_attention",
        "consecutive_failures_to_alert": "1",
        "match_key": "",
        "parser_pack_id": "",
    }
    only_dental = read_csv((await export(client, client_id=dental["id"])).text)
    assert [row["job"] for row in only_dental] == ["Nightly server backup"]


async def test_a_round_trip_changes_nothing_and_one_bad_row_is_reported(
    client: httpx.AsyncClient, csrf: str
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    hostile = await make_client(client, csrf, "+Fictional Plus Ltd")
    await make_job(client, csrf, dental["id"], "Nightly server backup")
    await make_job(
        client,
        csrf,
        hostile["id"],
        "=Weekly image backup",
        schedule_kind="interval",
        schedule_expr="1h30m",
        grace_minutes=0,
        warning_policy="warning_counts_ok",
        consecutive_failures_to_alert=3,
        parser_pack_id="generic-keywords",
    )
    before = (await export(client)).text

    again = await upload(client, csrf, before)
    assert again.status_code == 200, again.text
    assert again.json() == {
        "created": 0,
        "updated": 2,
        "clients_created": 0,
        "errors": [],
        "dry_run": False,
    }
    assert (await export(client)).text == before

    # One more row for a new client and one row with an impossible schedule.
    extra = (
        f"{LAW},Document server backup,backup,cron,0 22 * * 1-5,Europe/Lisbon,"
        "240,60,15,warning_is_attention,2,docsrv,\r\n"
        f"{LAW},Broken job,backup,cron,61 * * * *,UTC,,,,,,,\r\n"
    )
    imported = await upload(client, csrf, before + extra)
    result = imported.json()
    assert result["created"] == 1
    assert result["updated"] == 2
    assert result["clients_created"] == 1
    assert [problem["row"] for problem in result["errors"]] == [5]
    assert "cron" in result["errors"][0]["message"]
    rows = read_csv((await export(client)).text)
    # The order follows the database collation, which may skip punctuation.
    assert sorted((row["client"], row["job"]) for row in rows) == [
        ("'+Fictional Plus Ltd", "'=Weekly image backup"),
        (DENTAL, "Nightly server backup"),
        (LAW, "Document server backup"),
    ]
    law_row = next(row for row in rows if row["client"] == LAW)
    assert (law_row["max_runtime_minutes"], law_row["match_key"]) == ("240", "docsrv")


async def test_import_reports_each_bad_row_by_number(
    client: httpx.AsyncClient, csrf: str
) -> None:
    text = (
        "client,job,schedule_kind,schedule_expr,timezone,grace_minutes\n"
        f"{DENTAL},Nightly server backup,daily,23:00,Europe/Lisbon,\n"
        f"{DENTAL},Bad zone,daily,23:00,Mars/Olympus_Mons,\n"
        f"{DENTAL},Bad number,daily,23:00,UTC,soon\n"
        f",Missing client,daily,23:00,UTC,\n"
        f"{DENTAL},nightly SERVER backup,daily,22:00,UTC,\n"
        f"{DENTAL},Too many cells,daily,22:00,UTC,1,extra\n"
        "\n"
        f"{FREIGHT},Never fires,cron,0 0 30 2 *,UTC,\n"
    )
    response = await upload(client, csrf, text)
    assert response.status_code == 200
    result = response.json()
    assert result["created"] == 1
    assert result["clients_created"] == 1
    errors = {problem["row"]: problem["message"] for problem in result["errors"]}
    assert sorted(errors) == [3, 4, 5, 6, 7, 9]
    assert "IANA" in errors[3]
    assert errors[4].startswith("grace_minutes:")
    assert "soon" not in errors[4]
    assert errors[5].startswith("client:")
    assert errors[6] == "Same client and job as row 2."
    assert "more cells" in errors[7]
    assert "never fires" in errors[9]
    listed = (await client.get("/api/v1/clients")).json()["items"]
    assert [item["name"] for item in listed] == [DENTAL]


async def test_a_dry_run_saves_nothing(client: httpx.AsyncClient, csrf: str) -> None:
    text = (
        "client,job,schedule_kind,schedule_expr,timezone\n"
        f"{DENTAL},Nightly server backup,daily,23:00,Europe/Lisbon\n"
    )
    response = await upload(client, csrf, text, dry_run="true")
    assert response.json() == {
        "created": 1,
        "updated": 0,
        "clients_created": 1,
        "errors": [],
        "dry_run": True,
    }
    assert (await client.get("/api/v1/clients")).json()["items"] == []
    assert (await client.get("/api/v1/jobs")).json()["items"] == []


@pytest.mark.parametrize(
    ("content", "detail"),
    [
        (b"", "empty"),
        (b"\xff\xfeclient", "UTF-8"),
        (b"client,job\n", "Missing column: schedule_expr, schedule_kind, timezone."),
        (HEADER.encode() + b",secret\n", "Unknown column: secret."),
        (b"client,client,job,schedule_kind,schedule_expr,timezone\n", "twice"),
        (b'client,job,schedule_kind,schedule_expr,timezone\n"open', "valid CSV"),
    ],
)
async def test_unusable_files_are_refused(
    client: httpx.AsyncClient, csrf: str, content: bytes, detail: str
) -> None:
    response = await upload(client, csrf, content)
    assert response.status_code == 422
    assert detail in response.json()["detail"]


async def test_too_many_rows_or_bytes_are_refused(
    client: httpx.AsyncClient, csrf: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.v1.jobs_csv.MAX_IMPORT_ROWS", 2)
    rows = "".join(f"{DENTAL},Job {n},daily,23:00,UTC\n" for n in range(3))
    text = "client,job,schedule_kind,schedule_expr,timezone\n" + rows
    many = await upload(client, csrf, text)
    assert many.status_code == 422
    assert "more than 2 rows" in many.json()["detail"]
    big = await upload(client, csrf, b"x" * (1024 * 1024 + 1))
    assert big.status_code == 422
    assert "larger than" in big.json()["detail"]
    huge = await upload(client, csrf, b"x" * (2 * 1024 * 1024))
    assert huge.status_code == 413


async def test_a_read_token_exports_but_cannot_import(
    app: FastAPI, client: httpx.AsyncClient, csrf: str
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    await make_job(client, csrf, dental["id"], "Nightly server backup")
    token = await client.post(
        "/api/v1/tokens",
        json={"label": "synthetic export", "scope": "read"},
        headers={CSRF_HEADER: csrf},
    )
    reader: dict[str, Any] = {"Authorization": f"Bearer {token.json()['token']}"}
    async with another_browser(app) as script:
        exported = await script.get("/api/v1/jobs/export.csv", headers=reader)
        assert exported.status_code == 200
        assert len(read_csv(exported.text)) == 1
        refused = await script.post(
            "/api/v1/jobs/import.csv",
            files={"file": ("jobs.csv", exported.content, "text/csv")},
            headers=reader,
        )
        assert refused.status_code == 401


async def test_a_missing_column_keeps_the_stored_value(
    client: httpx.AsyncClient, csrf: str
) -> None:
    dental = await make_client(client, csrf, DENTAL)
    job = await make_job(
        client, csrf, dental["id"], "Disk check", kind="script", grace_minutes=60
    )
    text = (
        "client,job,schedule_kind,schedule_expr,timezone,grace_minutes\n"
        f"{DENTAL},Disk check,cron,0 6 * * *,UTC,\n"
    )
    assert (await upload(client, csrf, text)).json()["updated"] == 1
    changed = (await client.get(f"/api/v1/jobs/{job['id']}")).json()
    assert changed["kind"] == "script"
    assert changed["grace_minutes"] == 120
    assert (changed["schedule_kind"], changed["schedule_expr"]) == ("cron", "0 6 * * *")
