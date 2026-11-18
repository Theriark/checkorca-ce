"""Alembic environment: async engine on asyncpg.

The URL comes from the "database_url" attribute (python -m app migrate) or from
DATABASE_URL, never from Settings, so alembic also runs without SECRET_KEY and
FERNET_KEY.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.db.base import Base

# Held for the length of a migration, so two processes that start together
# (web and all, or two replicas) never migrate at once.
MIGRATION_LOCK_KEY = 4_270_001

config = context.config
# python -m app migrate keeps the logging of its own process.
configure_logger = config.attributes.get("configure_logger", True)
if config.config_file_name is not None and configure_logger:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def database_url() -> str:
    url = config.attributes.get("database_url") or os.environ.get("DATABASE_URL", "")
    if not url.strip():
        raise RuntimeError("DATABASE_URL is required to run migrations")
    return url.strip()


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        # Transaction-level lock, released at commit or rollback. The current
        # revision is read after it is taken, so a second process finds nothing
        # left to do.
        connection.execute(text(f"SELECT pg_advisory_xact_lock({MIGRATION_LOCK_KEY})"))
        context.run_migrations()


async def run_async_migrations() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = database_url()
    connectable = async_engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
