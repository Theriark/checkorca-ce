"""Command line: python -m app {web,worker,all,migrate,seed}.

Without a command the ROLE setting decides (web, worker or all). The image runs
"all": web and worker in one process, as Dokploy deploys it. web and all apply
the migrations before the HTTP port opens.
"""

import argparse
import asyncio
import logging
import signal
import sys
from collections.abc import Sequence
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config

from app.main import create_app
from app.settings import Settings, SettingsError, load_settings
from app.worker.loop import run_worker

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = ("web", "worker", "all", "migrate", "seed")

logger = logging.getLogger("app")


def alembic_config(settings: Settings) -> Config:
    """Alembic configuration; migrations/env.py reads the URL from attributes."""
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    config.attributes["database_url"] = settings.database_url.get_secret_value()
    # Keep the logging set up by this process.
    config.attributes["configure_logger"] = False
    return config


def migrate(settings: Settings) -> None:
    """Upgrade the database to the newest revision."""
    command.upgrade(alembic_config(settings), "head")
    logger.info("database migrated to head")


def seed(settings: Settings) -> None:
    """Development seed. The accounts arrive in phase C1, demo data in C8."""
    logger.info("seed: nothing to seed yet for %s", settings.base_url)


async def serve(settings: Settings, with_worker: bool) -> None:
    """Serve HTTP on settings.port; with_worker also runs the worker loop."""
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings),
            host="0.0.0.0",
            port=settings.port,
            log_level=settings.log_level,
            server_header=False,
        )
    )
    if not with_worker:
        await server.serve()
        return
    stop = asyncio.Event()
    worker = asyncio.create_task(run_worker(stop))
    try:
        await server.serve()
    finally:
        stop.set()
        await worker


async def work() -> None:
    """Run the worker loop until SIGTERM or SIGINT."""
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, stop.set)
    await run_worker(stop)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app", description="Checkorca-CE")
    parser.add_argument(
        "command",
        nargs="?",
        choices=COMMANDS,
        help="what to run (default: the ROLE setting)",
    )
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
    except SettingsError as error:
        print(f"checkorca: {error}", file=sys.stderr)
        return 2
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    name: str = args.command or settings.role
    if name == "migrate":
        migrate(settings)
    elif name == "seed":
        seed(settings)
    elif name == "worker":
        asyncio.run(work())
    else:
        migrate(settings)
        asyncio.run(serve(settings, with_worker=name == "all"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
