"""FastAPI dependency providers.

Extended in slice 1b with `get_password_hasher`, `get_token_service`, and
`get_current_user_id`.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports import Clock
from app.infrastructure.clock import SystemClock
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork


def get_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """Return the process-wide session factory stored on `app.state`."""
    factory: async_sessionmaker[AsyncSession] = request.app.state.session_factory
    return factory


async def get_session(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> AsyncIterator[AsyncSession]:
    """Yield a request-scoped `AsyncSession` built from the app's session factory."""
    async with session_factory() as session:
        yield session


def get_uow(
    session_factory: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_session_factory)
    ],
) -> SqlAlchemyUnitOfWork:
    """Build a per-request `UnitOfWork`. The use case opens the transaction."""
    return SqlAlchemyUnitOfWork(session_factory)


def get_clock() -> Clock:
    """Provide the real, UTC system clock."""
    return SystemClock()
