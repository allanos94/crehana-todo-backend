"""Shared integration-test fixtures (design ADR-14).

- `postgres_url`: a session-scoped sync Testcontainers Postgres, started once.
- `migrated_engine`: a session-scoped async engine with the schema brought to
  `head` via Alembic, using connection sharing (no `asyncio.run` inside a
  running loop, since the upgrade happens through `engine.begin()`).
- `session_factory` / `db_session`: a per-test connection with a savepoint
  transaction, so a use case's `commit()` only releases a savepoint, and
  teardown rolls the whole thing back.
"""

from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.community.postgres import PostgresContainer


def _alembic_config(url: str) -> Config:
    """Build an Alembic `Config` pointed at this repo's `alembic.ini`."""
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as container:
        yield container.get_connection_url()


@pytest_asyncio.fixture(scope="session")
async def migrated_engine(postgres_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(postgres_url)
    config = _alembic_config(postgres_url)

    def _upgrade(connection: Connection) -> None:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    async with engine.begin() as connection:
        await connection.run_sync(_upgrade)

    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def session_factory(
    migrated_engine: AsyncEngine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    connection = await migrated_engine.connect()
    transaction = await connection.begin()
    factory = async_sessionmaker(
        bind=connection,
        join_transaction_mode="create_savepoint",
        expire_on_commit=False,
    )
    try:
        yield factory
    finally:
        await transaction.rollback()
        await connection.close()


@pytest_asyncio.fixture
async def db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session
