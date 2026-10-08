"""Async SQLAlchemy engine and session factory construction.

This is the minimal persistence primitive needed by `/health/ready` in the
bootstrap slice. The declarative base, ORM models, mappers, repositories, and
Unit of Work land in slice 1a (`feature/auth-foundation`).
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def create_engine(database_url: str) -> AsyncEngine:
    """Create the process-wide async engine with connection pre-ping enabled."""
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create a session factory bound to `engine`, with `expire_on_commit=False`."""
    return async_sessionmaker(engine, expire_on_commit=False)
