"""Task-list CRUD endpoints (task-lists spec): owner-scoped create,
retrieve, list, update, delete. Non-owner/nonexistent both -> 404, never
403 (design ADR-06).
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.application.ports import Clock, UnitOfWork
from app.application.task_lists.dto import (
    CreateTaskListCommand,
    DeleteTaskListCommand,
    GetTaskListCommand,
    ListTaskListsCommand,
    UpdateTaskListCommand,
)
from app.application.task_lists.use_cases import (
    CreateTaskList,
    DeleteTaskList,
    GetTaskList,
    ListTaskLists,
    UpdateTaskList,
)
from app.infrastructure.api.dependencies import CurrentUserId, get_clock, get_uow
from app.infrastructure.api.schemas.common import ErrorResponse
from app.infrastructure.api.schemas.task_lists import (
    CreateTaskListRequest,
    TaskListResponse,
    UpdateTaskListRequest,
)

router = APIRouter(prefix="/api/v1/lists", tags=["task-lists"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TaskListResponse,
    responses={
        401: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def create_task_list(
    payload: CreateTaskListRequest,
    actor_id: CurrentUserId,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> TaskListResponse:
    use_case = CreateTaskList(uow, clock)
    result = await use_case.execute(
        CreateTaskListCommand(
            actor_id=actor_id, name=payload.name, description=payload.description
        )
    )
    return TaskListResponse.model_validate(result, from_attributes=True)


@router.get(
    "",
    response_model=list[TaskListResponse],
    responses={401: {"model": ErrorResponse}},
)
async def list_task_lists(
    actor_id: CurrentUserId,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> list[TaskListResponse]:
    use_case = ListTaskLists(uow)
    results = await use_case.execute(ListTaskListsCommand(actor_id=actor_id))
    return [
        TaskListResponse.model_validate(result, from_attributes=True)
        for result in results
    ]


@router.get(
    "/{list_id}",
    response_model=TaskListResponse,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_task_list(
    list_id: UUID,
    actor_id: CurrentUserId,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> TaskListResponse:
    use_case = GetTaskList(uow)
    result = await use_case.execute(
        GetTaskListCommand(actor_id=actor_id, list_id=list_id)
    )
    return TaskListResponse.model_validate(result, from_attributes=True)


@router.patch(
    "/{list_id}",
    response_model=TaskListResponse,
    responses={
        401: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
)
async def update_task_list(
    list_id: UUID,
    payload: UpdateTaskListRequest,
    actor_id: CurrentUserId,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    clock: Annotated[Clock, Depends(get_clock)],
) -> TaskListResponse:
    use_case = UpdateTaskList(uow, clock)
    fields = payload.model_dump(exclude_unset=True)
    result = await use_case.execute(
        UpdateTaskListCommand(actor_id=actor_id, list_id=list_id, **fields)
    )
    return TaskListResponse.model_validate(result, from_attributes=True)


@router.delete(
    "/{list_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def delete_task_list(
    list_id: UUID,
    actor_id: CurrentUserId,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> None:
    use_case = DeleteTaskList(uow)
    await use_case.execute(DeleteTaskListCommand(actor_id=actor_id, list_id=list_id))
