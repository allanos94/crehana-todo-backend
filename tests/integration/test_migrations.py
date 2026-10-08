"""Migration round-trip test (design ADR-09/ADR-14).

Uses its own fresh database (`CREATE DATABASE` on the shared container) so
it never interferes with `migrated_engine`'s already-migrated schema.
"""

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, inspect
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


def _alembic_config(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    return config


def _with_database(url: str, db_name: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{db_name}"


async def test_downgrade_base_then_upgrade_head(postgres_url: str) -> None:
    db_name = "migration_roundtrip_test"
    admin_engine = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as connection:
        await connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{db_name}"')
        await connection.exec_driver_sql(f'CREATE DATABASE "{db_name}"')
    await admin_engine.dispose()

    fresh_url = _with_database(postgres_url, db_name)
    engine = create_async_engine(fresh_url)
    config = _alembic_config(fresh_url)

    def _upgrade(connection: Connection) -> None:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    def _downgrade(connection: Connection) -> None:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")

    async with engine.begin() as connection:
        await connection.run_sync(_upgrade)
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
    assert "users" in tables

    async with engine.begin() as connection:
        await connection.run_sync(_downgrade)
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda c: inspect(c).get_table_names())
    assert "users" not in tables

    async with engine.begin() as connection:
        await connection.run_sync(_upgrade)

    await engine.dispose()
