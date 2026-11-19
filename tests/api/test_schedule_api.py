"""schedule/preview: the next times for the job editor, or a readable error."""

import httpx
import pytest

from app.db.models import AppUser
from helpers import ADMIN_EMAIL, ADMIN_PASSWORD, CSRF_HEADER, FakeClock, sign_in


@pytest.fixture
async def csrf(client: httpx.AsyncClient, admin: AppUser) -> str:
    return await sign_in(client, ADMIN_EMAIL, ADMIN_PASSWORD)


async def preview(
    client: httpx.AsyncClient, csrf: str, **body: object
) -> dict[str, object]:
    response = await client.post(
        "/api/v1/schedule/preview", json=body, headers={CSRF_HEADER: csrf}
    )
    assert response.status_code == 200, response.text
    answer: dict[str, object] = response.json()
    return answer


async def test_daily_2300_lisbon_gives_five_times(
    client: httpx.AsyncClient, csrf: str
) -> None:
    # The fake clock reads Monday 4 January 2027, 09:00 UTC.
    answer = await preview(
        client, csrf, kind="daily", expr="23:00", timezone="Europe/Lisbon"
    )
    assert answer == {
        "next": [
            "2027-01-04T23:00:00Z",
            "2027-01-05T23:00:00Z",
            "2027-01-06T23:00:00Z",
            "2027-01-07T23:00:00Z",
            "2027-01-08T23:00:00Z",
        ],
        "local": [
            "2027-01-04T23:00:00+00:00",
            "2027-01-05T23:00:00+00:00",
            "2027-01-06T23:00:00+00:00",
            "2027-01-07T23:00:00+00:00",
            "2027-01-08T23:00:00+00:00",
        ],
        "error": None,
        "field": None,
    }


async def test_after_and_count_cross_the_spring_change(
    client: httpx.AsyncClient, csrf: str
) -> None:
    answer = await preview(
        client,
        csrf,
        kind="cron",
        expr="30 1 * * *",
        timezone="Europe/Lisbon",
        after="2027-03-26T12:00:00Z",
        count=3,
    )
    assert answer["local"] == [
        "2027-03-27T01:30:00+00:00",
        "2027-03-28T02:00:00+01:00",
        "2027-03-29T01:30:00+01:00",
    ]


async def test_an_interval_counts_from_the_anchor_or_now(
    client: httpx.AsyncClient, csrf: str, clock: FakeClock
) -> None:
    from_now = await preview(
        client, csrf, kind="interval", expr="6h", timezone="UTC", count=2
    )
    assert from_now["next"] == ["2027-01-04T15:00:00Z", "2027-01-04T21:00:00Z"]
    anchored = await preview(
        client,
        csrf,
        kind="interval",
        expr="6h",
        timezone="UTC",
        count=1,
        anchor="2027-01-04T08:30:00Z",
    )
    assert anchored["next"] == ["2027-01-04T14:30:00Z"]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"kind": "cron", "expr": "61 * * * *", "timezone": "UTC"}, "schedule_expr"),
        ({"kind": "cron", "expr": "0 0 30 2 *", "timezone": "UTC"}, "schedule_expr"),
        ({"kind": "daily", "expr": "23:00", "timezone": "Nowhere"}, "timezone"),
    ],
)
async def test_an_unusable_schedule_is_an_answer_not_a_failure(
    client: httpx.AsyncClient, csrf: str, body: dict[str, str], field: str
) -> None:
    answer = await preview(client, csrf, **body)
    assert answer["next"] == []
    assert answer["field"] == field
    assert isinstance(answer["error"], str) and answer["error"].endswith(".")


async def test_every_minute_of_a_few_months_previews_outside_them(
    client: httpx.AsyncClient, csrf: str
) -> None:
    """Code review M1: this answered 500 when next_n listed the whole window."""
    answer = await preview(
        client,
        csrf,
        kind="cron",
        expr="* * * 1-3 *",
        timezone="Europe/Lisbon",
        after="2026-11-19T11:54:00Z",
        count=20,
    )
    assert answer["error"] is None
    times = answer["next"]
    assert isinstance(times, list) and len(times) == 20
    assert times[:2] == ["2027-01-01T00:00:00Z", "2027-01-01T00:01:00Z"]


# Code review L3: times the schedule library cannot add its padding to.
SIX_HOURS = {"kind": "interval", "expr": "6h", "timezone": "UTC"}
OUT_OF_RANGE = [
    {**SIX_HOURS, "after": "9999-12-30T00:00:00Z"},
    {**SIX_HOURS, "after": "0001-01-01T00:00:00Z"},
    {**SIX_HOURS, "after": "1969-12-31T23:59:59Z"},
    {**SIX_HOURS, "anchor": "0001-01-01T00:00:00Z"},
    {**SIX_HOURS, "anchor": "2200-01-01T00:00:01Z"},
]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"kind": "weekly", "expr": "x", "timezone": "UTC"},
        {"kind": "daily", "expr": "23:00", "timezone": "UTC", "count": 21},
        {"kind": "daily", "expr": "23:00", "timezone": "UTC", "after": "2027-01-04"},
        *OUT_OF_RANGE,
    ],
)
async def test_malformed_requests_are_422(
    client: httpx.AsyncClient, csrf: str, body: dict[str, object]
) -> None:
    response = await client.post(
        "/api/v1/schedule/preview", json=body, headers={CSRF_HEADER: csrf}
    )
    assert response.status_code == 422


async def test_the_preview_needs_a_session(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/schedule/preview",
        json={"kind": "daily", "expr": "23:00", "timezone": "UTC"},
    )
    assert response.status_code == 401
