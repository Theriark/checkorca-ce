"""The client address: behind a trusted proxy, and only real IP addresses.

On Dokploy, uvicorn's ProxyHeadersMiddleware trusts the proxy network named in
FORWARDED_ALLOW_IPS and takes the right-most untrusted X-Forwarded-For hop.
The sign-in buckets and the audit trail then follow the real client, and a
forged left-most entry changes nothing. Here the ASGI test client connects from
127.0.0.1, which plays the trusted proxy.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.api.deps import client_ip
from app.db.models import AuditEvent

LOGIN = "/api/v1/auth/login"
ATTEMPT = {"email": "nobody@example.com", "password": "Synthetic-" + "w" * 12}


def behind_proxy(app: FastAPI) -> httpx.AsyncClient:
    proxied = ProxyHeadersMiddleware(app, trusted_hosts="127.0.0.1")
    transport = httpx.ASGITransport(app=proxied)
    return httpx.AsyncClient(transport=transport, base_url="https://test")


def forwarded(value: str) -> dict[str, str]:
    return {"X-Forwarded-For": value}


async def sign_in_status(proxy: httpx.AsyncClient, headers: dict[str, str]) -> int:
    answer = await proxy.post(LOGIN, json=ATTEMPT, headers=headers)
    return answer.status_code


async def test_sign_in_buckets_follow_the_forwarded_client(
    app: FastAPI, client: httpx.AsyncClient, db_engine: AsyncEngine
) -> None:
    first = forwarded("192.0.2.10")
    # A forged left-most entry: uvicorn still takes the hop the proxy added.
    forged = forwarded("192.0.2.99, 192.0.2.10")
    other = forwarded("192.0.2.11")
    async with behind_proxy(app) as proxy:
        for _ in range(10):
            assert await sign_in_status(proxy, first) == 401
        assert await sign_in_status(proxy, first) == 429
        assert await sign_in_status(proxy, forged) == 429
        assert await sign_in_status(proxy, other) == 401

    async with db_engine.connect() as connection:
        addresses = set((await connection.execute(select(AuditEvent.ip))).scalars())
    assert addresses == {"192.0.2.10", "192.0.2.11"}


@pytest.mark.parametrize(
    ("peer", "expected"),
    [
        (("192.0.2.10", 443), "192.0.2.10"),
        (("2001:db8::1", 443), "2001:db8::1"),
        (("not-an-address", 443), None),
        (("192.0.2." + "1" * 60, 443), None),
        (None, None),
    ],
)
def test_only_ip_addresses_are_client_addresses(
    peer: Any, expected: str | None
) -> None:
    request = Request({"type": "http", "client": peer, "headers": []})
    assert client_ip(request) == expected
