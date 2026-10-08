"""Alembic async environment (design ADR-09).

The database URL always comes from `get_settings()`, never from
`alembic.ini`. Supports connection sharing: when the caller sets
`config.attributes["connection"]` (used by the integration test harness to
drive migrations inside an already-open async connection), migrations run
directly against it instead of opening a new engine.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, async_engine_from_config

from app.infrastructure.config import get_settings
from app.infrastructure.db import (  # noqa: F401  (registers tables on Base.metadata)
    models,
)
from app.infrastructure.db.base import Base

config = context.config

if config.config_file_name is not None:
    # `disable_existing_loggers=False`: the default (`True`) silently
    # disables every logger that already exists at this point --
    # including `app.notifications` and any other `app.*` logger created
    # at import time -- for loggers not named in `alembic.ini`'s
    # `[loggers]` section. In the test suite, Alembic's `env.py` runs in
    # the same process as the API code (unlike the real `alembic upgrade
    # head` CLI, a separate process), so the default would permanently
    # silence application logging for the rest of the session the first
    # time any integration test runs migrations.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _get_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL without a live DB connection."""
    context.configure(
        url=_get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _get_url()
    connectable: AsyncEngine = async_engine_from_config(
        configuration, prefix="sqlalchemy.", poolclass=pool.NullPool
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations against a live DB connection, async or injected."""
    injected_connection = config.attributes.get("connection")
    if injected_connection is not None:
        do_run_migrations(injected_connection)
        return
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
