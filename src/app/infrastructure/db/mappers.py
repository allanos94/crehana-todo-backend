"""ORM <-> domain mapping functions.

Domain objects are plain dataclasses, never ORM instances, so lazy loading
is structurally impossible once a row crosses this boundary (design ADR-07).
"""

from app.domain.task import Task
from app.domain.task_list import TaskList
from app.domain.user import User
from app.infrastructure.db.models import TaskListModel, TaskModel, UserModel


def user_to_model(user: User) -> UserModel:
    return UserModel(
        id=user.id,
        email=user.email,
        hashed_password=user.hashed_password,
        created_at=user.created_at,
    )


def model_to_user(model: UserModel) -> User:
    return User(
        id=model.id,
        email=model.email,
        hashed_password=model.hashed_password,
        created_at=model.created_at,
    )


def task_list_to_model(task_list: TaskList) -> TaskListModel:
    return TaskListModel(
        id=task_list.id,
        owner_id=task_list.owner_id,
        name=task_list.name,
        description=task_list.description,
        created_at=task_list.created_at,
        updated_at=task_list.updated_at,
    )


def model_to_task_list(model: TaskListModel) -> TaskList:
    return TaskList(
        id=model.id,
        owner_id=model.owner_id,
        name=model.name,
        description=model.description,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def task_to_model(task: Task) -> TaskModel:
    return TaskModel(
        id=task.id,
        list_id=task.list_id,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        due_date=task.due_date,
        assignee_id=task.assignee_id,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def model_to_task(model: TaskModel) -> Task:
    return Task(
        id=model.id,
        list_id=model.list_id,
        title=model.title,
        description=model.description,
        status=model.status,
        priority=model.priority,
        due_date=model.due_date,
        assignee_id=model.assignee_id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )
