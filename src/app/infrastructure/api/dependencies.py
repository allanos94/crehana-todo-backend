"""FastAPI dependency providers.

Extended in slice 1a with `get_uow` and `get_clock`, and in slice 1b with
`get_password_hasher`, `get_token_service`, and `get_current_user_id`.
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


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
