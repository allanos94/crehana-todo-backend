"""`SqlAlchemyUnitOfWork`: one `AsyncSession` per use-case execution, with
`IntegrityError` -> domain-error translation keyed on constraint name
(design ADR-07). Unknown constraint names are re-raised, never swallowed.
"""

from types import TracebackType
from typing import Self

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.domain.exceptions import EmailAlreadyRegisteredError
from app.infrastructure.db.repositories import SqlAlchemyUserRepository

_CONSTRAINT_ERRORS: dict[str, type[Exception]] = {
    "uq_users_email": EmailAlreadyRegisteredError,
}


class SqlAlchemyUnitOfWork:
    """Opens one `AsyncSession` on `__aenter__`; rolls back unless committed."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None
        self._committed = False

    async def __aenter__(self) -> Self:
        self._session = self._session_factory()
        self._committed = False
        self.users: SqlAlchemyUserRepository = SqlAlchemyUserRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        assert self._session is not None
        if not self._committed:
            await self._session.rollback()
        await self._session.close()
        self._session = None

    async def commit(self) -> None:
        assert self._session is not None
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            error_cls = _CONSTRAINT_ERRORS.get(_constraint_name(exc))
            if error_cls is None:
                raise
            raise error_cls() from exc
        else:
            self._committed = True


def _constraint_name(exc: IntegrityError) -> str:
    """Read the asyncpg constraint name from `IntegrityError.orig.__cause__`."""
    cause = getattr(exc.orig, "__cause__", None)
    constraint_name = getattr(cause, "constraint_name", None)
    return str(constraint_name) if constraint_name else ""
