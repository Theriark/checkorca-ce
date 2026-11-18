"""The worker loop ticks until it is asked to stop."""

import asyncio
import importlib

import pytest

from app.worker.loop import run_worker


async def test_worker_ticks_until_stopped() -> None:
    stop = asyncio.Event()
    task = asyncio.create_task(run_worker(stop, tick_seconds=0.01))
    await asyncio.sleep(0.05)
    assert not task.done()
    stop.set()
    await asyncio.wait_for(task, timeout=1)


async def test_worker_returns_at_once_when_already_stopped() -> None:
    stop = asyncio.Event()
    stop.set()
    await asyncio.wait_for(run_worker(stop), timeout=1)


@pytest.mark.parametrize("name", ["app.schedule", "app.evaluator", "app.parsers"])
def test_core_packages_exist_for_the_strict_gates(name: str) -> None:
    # mypy strict and the 95 percent coverage gate apply to these packages.
    assert importlib.import_module(name).__all__ == []
