"""FastAPI dependency providers.

Extended in slice 1b with `get_password_hasher`, `get_token_service`, and
`get_current_user_id`.
"""

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.exceptions import NotAuthenticatedError
from app.application.ports import Clock, PasswordHasher, TokenService, TokenType
from app.infrastructure.clock import SystemClock
from app.infrastructure.config import get_settings
from app.infrastructure.db.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.security.jwt import JwtTokenService
from app.infrastructure.security.password import Argon2PasswordHasher

_bearer_scheme = HTTPBearer(auto_error=False)


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


def get_password_hasher() -> PasswordHasher:
    """Provide the real Argon2 password hasher."""
    return Argon2PasswordHasher()


def get_token_service(
    clock: Annotated[Clock, Depends(get_clock)],
) -> TokenService:
    """Provide the real JWT token service, keyed from `Settings`."""
    settings = get_settings()
    return JwtTokenService(settings.jwt_secret_key.get_secret_value(), clock)


async def get_current_user_id(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> UUID:
    """Resolve the authenticated actor's id from a bearer access token.

    A missing `Authorization` header raises `NotAuthenticatedError`; an
    invalid, expired, or wrong-typed token raises `InvalidTokenError` (both
    401, per the error contract).
    """
    if credentials is None:
        raise NotAuthenticatedError()
    return tokens.decode(credentials.credentials, TokenType.ACCESS)


CurrentUserId = Annotated[UUID, Depends(get_current_user_id)]
