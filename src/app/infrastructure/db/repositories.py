"""SQLAlchemy-backed repository implementations (design ADR-05/ADR-07)."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.user import User
from app.infrastructure.db.mappers import model_to_user, user_to_model
from app.infrastructure.db.models import UserModel


class SqlAlchemyUserRepository:
    """Implements `UserRepository` against one request-scoped `AsyncSession`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, user: User) -> None:
        self._session.add(user_to_model(user))

    async def get_by_id(self, user_id: UUID) -> User | None:
        model = await self._session.get(UserModel, user_id)
        return model_to_user(model) if model is not None else None

    async def get_by_email(self, email: str) -> User | None:
        statement = select(UserModel).where(UserModel.email == email)
        result = await self._session.execute(statement)
        model = result.scalar_one_or_none()
        return model_to_user(model) if model is not None else None
