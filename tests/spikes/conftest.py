"""Fixtures of the C0-B spikes (docs/spikes.md).

The spikes prove the libraries and PostgreSQL features later phases rely on. They
print their measurements next to the test result, so a CI log shows the numbers
docs/spikes.md records.
"""

from collections.abc import AsyncIterator, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy.pool import NullPool

from app.settings import load_settings

Report = Callable[..., None]


@pytest.fixture
def report(capsys: pytest.CaptureFixture[str]) -> Report:
    """Print "spike <name>: key=value ..." to the terminal, also under pytest -q."""

    def emit(spike: str, **values: object) -> None:
        line = " ".join(f"{key}={value}" for key, value in values.items())
        with capsys.disabled():
            print(f"\nspike {spike}: {line}")

    return emit


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """An engine on the test database without a pool.

    Every connect() opens its own server session and closing the connection ends
    it, which the advisory lock and SKIP LOCKED spikes need.
    """
    url = load_settings().database_url.get_secret_value()
    engine = create_async_engine(url, poolclass=NullPool)
    yield engine
    await engine.dispose()
