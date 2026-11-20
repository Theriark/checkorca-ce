"""The test bench runner: packs/test in a child process of the web process.

packs/test runs a user's regexes on a pasted mail. It never runs in the
worker process, and not on the web process's own threads either: the regex
module measures its timeout in CPU time of the whole process, and ROLE=all
runs the web app and the worker in one process, so a bench there would eat
into the 50 ms of every pattern the worker matches meanwhile.

Each test starts python -m app.parsers.bench with the request on stdin and
reads the answer from stdout. The child has its own CPU clock, the engine's
limits (50 ms per pattern, 5 s per mail) and its own CPU and memory limits;
it gets no environment beyond PATH and the locale, so no secret of the web
process. At most MAX_RUNNING children run at once, and one that has not
answered after the timeout is killed (503).
"""

import asyncio
import base64
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

# Seconds a test may take, starting the child included.
BENCH_TIMEOUT: Final = 20.0
MAX_RUNNING: Final = 2
# The answer holds at most 256 KiB of text and 200 results.
MAX_ANSWER_BYTES: Final = 8 * 1024 * 1024
ROOT: Final = Path(__file__).resolve().parent.parent.parent
COMMAND: Final = (sys.executable, "-m", "app.parsers.bench")

logger = logging.getLogger(__name__)


class BenchUnavailable(Exception):
    """The child did not answer in time or failed; the API answers 503."""


def child_environment() -> dict[str, str]:
    """PATH and the locale only: no setting of the web process."""
    kept = {name: os.environ[name] for name in ("PATH",) if name in os.environ}
    return {**kept, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}


class BenchRunner:
    """Starts one child per test; command and timeout can be replaced (tests)."""

    def __init__(
        self,
        command: Sequence[str] = COMMAND,
        timeout: float = BENCH_TIMEOUT,
        max_running: int = MAX_RUNNING,
    ) -> None:
        self.command = tuple(command)
        self.timeout = timeout
        self._running = asyncio.Semaphore(max_running)

    async def run(
        self, packs: Sequence[tuple[str, str]], pack: str | None, raw: bytes
    ) -> dict[str, Any]:
        """The child's answer for the mail; BenchUnavailable when there is none."""
        request = json.dumps(
            {
                "packs": [list(item) for item in packs],
                "pack": pack,
                "raw": base64.b64encode(raw).decode("ascii"),
            }
        ).encode("utf-8")
        async with self._running:
            child = await asyncio.create_subprocess_exec(
                *self.command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                cwd=ROOT,
                env=child_environment(),
            )
            try:
                output, _ = await asyncio.wait_for(
                    child.communicate(request), self.timeout
                )
            except TimeoutError:
                child.kill()
                await child.wait()
                logger.warning("test bench child killed after %s s", self.timeout)
                raise BenchUnavailable("The test took too long.") from None
        if child.returncode != 0 or len(output) > MAX_ANSWER_BYTES:
            # Never the child's output: it can hold the pasted mail.
            logger.warning("test bench child failed (exit %s)", child.returncode)
            raise BenchUnavailable("The test bench failed.")
        try:
            answer: dict[str, Any] = json.loads(output)
        except ValueError:
            logger.warning("test bench child answered no JSON")
            raise BenchUnavailable("The test bench failed.") from None
        return answer
