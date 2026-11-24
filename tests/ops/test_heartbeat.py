"""The external heartbeat watcher (phase C10): the dead-man URL.

One GET per tick through the SSRF guard, on the fake clock; an empty
EXTERNAL_HEARTBEAT_URL keeps the watcher off; a refused target or a failed
GET is logged as one sentence that never holds the URL (its path carries
the dead-man token) and never stops the ticks that follow.
"""

import pytest

from app.ops.heartbeat import external_heartbeat
from app.settings import load_settings
from app.worker.loop import WorkerContext, build_context
from helpers import URL_CANARY, FakeClock, HttpCapture, http_answer


async def watch_context(
    monkeypatch: pytest.MonkeyPatch, clock: FakeClock, url: str | None
) -> WorkerContext:
    """A worker context whose settings name url (None keeps the watcher
    off); the capture server runs on a loopback address, so the outbound
    rule allows private targets for the calls that should reach it."""
    if url is not None:
        monkeypatch.setenv("EXTERNAL_HEARTBEAT_URL", url)
        monkeypatch.setenv("ALLOW_PRIVATE_TARGETS", "true")
    return build_context(load_settings(), clock)


async def test_each_tick_gets_the_url_once(
    monkeypatch: pytest.MonkeyPatch, clock: FakeClock
) -> None:
    """A GET per tick while the worker ticks: three ticks, three requests,
    no body, and the dead-man path never reaches the log."""
    capture = HttpCapture([http_answer(200)])
    await capture.start()
    try:
        context = await watch_context(monkeypatch, clock, capture.url)
        try:
            for _ in range(3):
                await external_heartbeat(context, clock.now())
                clock.advance(minutes=1)
        finally:
            await context.engine.dispose()
        assert len(capture.requests) == 3
        for request in capture.requests:
            assert request.line == f"GET {URL_CANARY} HTTP/1.1"
            assert request.body == {}
    finally:
        await capture.stop()


async def test_an_empty_url_keeps_the_watcher_off(
    monkeypatch: pytest.MonkeyPatch, clock: FakeClock
) -> None:
    """Without EXTERNAL_HEARTBEAT_URL (the safe default) nothing is called."""
    capture = HttpCapture([http_answer(200)])
    await capture.start()
    try:
        context = await watch_context(monkeypatch, clock, None)
        try:
            await external_heartbeat(context, clock.now())
            await external_heartbeat(context, clock.now())
        finally:
            await context.engine.dispose()
        assert capture.requests == []
    finally:
        await capture.stop()


async def test_a_refused_target_is_logged_and_the_tick_goes_on(
    monkeypatch: pytest.MonkeyPatch,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """127.0.0.1 without ALLOW_PRIVATE_TARGETS is refused by the guard: one
    warning names the host and the reason, the hook returns normally and
    nothing was sent."""
    capture = HttpCapture([http_answer(200)])
    await capture.start()
    try:
        monkeypatch.setenv("EXTERNAL_HEARTBEAT_URL", capture.url)
        context = build_context(load_settings(), clock)
        try:
            with caplog.at_level("WARNING", logger="app.ops.heartbeat"):
                await external_heartbeat(context, clock.now())
            assert capture.requests == []
            assert "the outbound heartbeat was refused" in caplog.text
            assert "loopback" in caplog.text
            assert URL_CANARY not in caplog.text
        finally:
            await context.engine.dispose()
    finally:
        await capture.stop()


async def test_a_failed_get_is_logged_and_the_next_tick_pings_again(
    monkeypatch: pytest.MonkeyPatch,
    clock: FakeClock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 500 answer is one warning line; the watcher keeps ticking."""
    failing = HttpCapture([http_answer(500)])
    await failing.start()
    try:
        context = await watch_context(monkeypatch, clock, failing.url)
        try:
            with caplog.at_level("WARNING", logger="app.ops.heartbeat"):
                await external_heartbeat(context, clock.now())
            assert "the outbound heartbeat failed" in caplog.text
            assert "answered 500" in caplog.text
            assert URL_CANARY not in caplog.text
            caplog.clear()
            clock.advance(minutes=1)
            await external_heartbeat(context, clock.now())
            assert len(failing.requests) == 2
            assert caplog.text.count("the outbound heartbeat failed") == 1
        finally:
            await context.engine.dispose()
    finally:
        await failing.stop()
