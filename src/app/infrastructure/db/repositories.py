"""SQLAlchemy-backed repository implementations (design ADR-05/ADR-07)."""

from uuid import UUID

from sqlalchemy import and_, func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.repositories import TaskCounts, TaskFilter
from app.domain.task import Task
from app.domain.task_list import TaskList
from app.domain.user import User
from app.domain.value_objects import TaskStatus
from app.infrastructure.db.mappers import (
    model_to_task,
    model_to_task_list,
    model_to_user,
    task_list_to_model,
    task_to_model,
    user_to_model,
)
from app.infrastructure.db.models import TaskListModel, TaskModel, UserModel


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


class SqlAlchemyTaskListRepository:
    """Implements `TaskListRepository` against one request-scoped
    `AsyncSession`. `name_exists` gives the application layer a friendly
    pre-check; the functional unique index backs it for race safety."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, task_list: TaskList) -> None:
        self._session.add(task_list_to_model(task_list))

    async def update(self, task_list: TaskList) -> None:
        model = await self._session.get(TaskListModel, task_list.id)
        assert model is not None
        model.name = task_list.name
        model.description = task_list.description
        model.updated_at = task_list.updated_at

    async def get(self, list_id: UUID) -> TaskList | None:
        model = await self._session.get(TaskListModel, list_id)
        return model_to_task_list(model) if model is not None else None

    async def list_by_owner(self, owner_id: UUID) -> list[TaskList]:
        statement = (
            select(TaskListModel)
            .where(TaskListModel.owner_id == owner_id)
            .order_by(TaskListModel.created_at)
        )
        result = await self._session.execute(statement)
        return [model_to_task_list(model) for model in result.scalars()]

    async def name_exists(
        self, owner_id: UUID, name: str, exclude_id: UUID | None = None
    ) -> bool:
        statement = select(TaskListModel.id).where(
            TaskListModel.owner_id == owner_id,
            func.lower(TaskListModel.name) == name.lower(),
        )
        if exclude_id is not None:
            statement = statement.where(TaskListModel.id != exclude_id)
        result = await self._session.execute(statement)
        return result.first() is not None

    async def delete(self, list_id: UUID) -> None:
        model = await self._session.get(TaskListModel, list_id)
        if model is not None:
            await self._session.delete(model)


class SqlAlchemyTaskRepository:
    """Implements `TaskRepository`'s basic CRUD against one request-scoped
    `AsyncSession`. Filters/counts (`search`) and `list_by_assignee` land
    in later slices (4, 5)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, task: Task) -> None:
        self._session.add(task_to_model(task))

    async def update(self, task: Task) -> None:
        model = await self._session.get(TaskModel, task.id)
        assert model is not None
        model.title = task.title
        model.description = task.description
        model.status = task.status
        model.priority = task.priority
        model.due_date = task.due_date
        model.assignee_id = task.assignee_id
        model.updated_at = task.updated_at

    async def get(self, task_id: UUID) -> Task | None:
        model = await self._session.get(TaskModel, task_id)
        return model_to_task(model) if model is not None else None

    async def delete(self, task_id: UUID) -> None:
        model = await self._session.get(TaskModel, task_id)
        if model is not None:
            await self._session.delete(model)

    async def search(
        self, list_id: UUID, filters: TaskFilter, limit: int, offset: int
    ) -> tuple[list[Task], TaskCounts]:
        """One `FILTER`-aggregate query for the list-wide counts plus one
        paged query for `items` (design ADR-10): `total_all`/`done_all`
        back `completion_percentage` and never apply `filters`;
        `total_filtered` and the page both do."""
        filter_conditions = []
        if filters.status is not None:
            filter_conditions.append(TaskModel.status == filters.status)
        if filters.priority is not None:
            filter_conditions.append(TaskModel.priority == filters.priority)
        filtered_predicate = and_(*filter_conditions) if filter_conditions else true()

        counts_statement = (
            select(
                func.count().label("total_all"),
                func.count()
                .filter(TaskModel.status == TaskStatus.DONE)
                .label("done_all"),
                func.count().filter(filtered_predicate).label("total_filtered"),
            )
        ).where(TaskModel.list_id == list_id)
        counts_row = (await self._session.execute(counts_statement)).one()
        counts = TaskCounts(
            total_all=counts_row.total_all,
            done_all=counts_row.done_all,
            total_filtered=counts_row.total_filtered,
        )

        page_statement = (
            select(TaskModel)
            .where(TaskModel.list_id == list_id, *filter_conditions)
            .order_by(TaskModel.created_at, TaskModel.id)
            .limit(limit)
            .offset(offset)
        )
        page_result = await self._session.execute(page_statement)
        items = [model_to_task(model) for model in page_result.scalars()]
        return items, counts

    async def list_by_assignee(
        self, user_id: UUID, limit: int, offset: int
    ) -> tuple[list[Task], int]:
        """List tasks assigned to `user_id` across every list (design
        ADR-10: `GET /users/me/tasks`, same `limit`/`offset`/ordering
        shape as `search`)."""
        count_statement = (
            select(func.count())
            .select_from(TaskModel)
            .where(TaskModel.assignee_id == user_id)
        )
        total = (await self._session.execute(count_statement)).scalar_one()

        page_statement = (
            select(TaskModel)
            .where(TaskModel.assignee_id == user_id)
            .order_by(TaskModel.created_at, TaskModel.id)
            .limit(limit)
            .offset(offset)
        )
        page_result = await self._session.execute(page_statement)
        items = [model_to_task(model) for model in page_result.scalars()]
        return items, total
