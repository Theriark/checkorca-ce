"""Helpers shared by the tests. Every value here is synthetic."""

import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI

TEST_SECRET_KEY = "s" * 40
# The all-zero Fernet key: valid in shape, protects nothing.
TEST_FERNET_KEY = base64.urlsafe_b64encode(bytes(32)).decode()
# Nothing listens on port 1: a database that is never reachable.
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://checkorca:unused@127.0.0.1:1/x"


@asynccontextmanager
async def running(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """A client for the app with its lifespan running (the engine is disposed)."""
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        client = httpx.AsyncClient(transport=transport, base_url="http://test")
        async with client:
            yield client
