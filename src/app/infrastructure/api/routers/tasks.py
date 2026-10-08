"""Task CRUD and status-change endpoints (tasks spec): owner-scoped
create, retrieve, update, delete, and the strict status state machine.
Non-owner/nonexistent both -> 404, never 403 (design ADR-06). Filters,
pagination, and `completion_percentage` land in Phase 7; the assignee
status-change path lands in Phase 8.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.application.ports import Clock, UnitOfWork
from app.application.tasks.dto import (
    ChangeTaskStatusCommand,
    CreateTaskCommand,
    DeleteTaskCommand,
    GetTaskCommand,
    UpdateTaskCommand,
)
from app.application.tasks.use_cases import (
    ChangeTaskStatus,
    CreateTask,
    DeleteTask,
    GetTask,
    UpdateTask,
)
from app.infrastructure.api.dependencies import CurrentUserId, get_clock, get_uow
from app.infrastructure.api.schemas.common import ErrorResponse
from app.infrastructure.api.schemas.tasks import (
    ChangeTaskStatusRequest,
    CreateTaskRequest,
    TaskResponse,
    UpdateTaskRequest,
)

router = APIRouter(prefix="/api/v1/lists/{list_id}/tasks", tags=["tasks"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def create_task(
    list_id: UUID,
    payload: CreateTaskRequest,
    actor_id: CurrentUserId,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> TaskResponse:
    use_case = CreateTask(uow, clock)
    result = await use_case.execute(
        CreateTaskCommand(
            actor_id=actor_id,
            list_id=list_id,
            title=payload.title,
            description=payload.description,
            priority=payload.priority,
            due_date=payload.due_date,
        )
    )
    return TaskResponse.model_validate(result, from_attributes=True)


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_task(
    list_id: UUID,
    task_id: UUID,
    actor_id: CurrentUserId,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> TaskResponse:
    use_case = GetTask(uow)
    result = await use_case.execute(
        GetTaskCommand(actor_id=actor_id, list_id=list_id, task_id=task_id)
    )
    return TaskResponse.model_validate(result, from_attributes=True)


@router.patch(
    "/{task_id}",
    response_model=TaskResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def update_task(
    list_id: UUID,
    task_id: UUID,
    payload: UpdateTaskRequest,
    actor_id: CurrentUserId,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> TaskResponse:
    use_case = UpdateTask(uow, clock)
    fields = payload.model_dump(exclude_unset=True)
    result = await use_case.execute(
        UpdateTaskCommand(actor_id=actor_id, list_id=list_id, task_id=task_id, **fields)
    )
    return TaskResponse.model_validate(result, from_attributes=True)


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def delete_task(
    list_id: UUID,
    task_id: UUID,
    actor_id: CurrentUserId,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> None:
    use_case = DeleteTask(uow)
    await use_case.execute(
        DeleteTaskCommand(actor_id=actor_id, list_id=list_id, task_id=task_id)
    )


@router.patch(
    "/{task_id}/status",
    response_model=TaskResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
    },
)
async def change_task_status(
    list_id: UUID,
    task_id: UUID,
    payload: ChangeTaskStatusRequest,
    actor_id: CurrentUserId,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> TaskResponse:
    use_case = ChangeTaskStatus(uow, clock)
    result = await use_case.execute(
        ChangeTaskStatusCommand(
            actor_id=actor_id,
            list_id=list_id,
            task_id=task_id,
            status=payload.status,
        )
    )
    return TaskResponse.model_validate(result, from_attributes=True)
