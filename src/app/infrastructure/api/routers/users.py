"""The authenticated-identity endpoint (user-auth spec: `GET /users/me`)
and the assignee's own cross-list task visibility (task-assignment spec:
`GET /users/me/tasks`)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.application.assignment.dto import ListMyAssignedTasksCommand
from app.application.assignment.use_cases import ListMyAssignedTasks
from app.application.auth.dto import GetCurrentUserCommand
from app.application.auth.use_cases import GetCurrentUser
from app.application.ports import UnitOfWork
from app.infrastructure.api.dependencies import CurrentUserId, get_uow
from app.infrastructure.api.schemas.common import ErrorResponse
from app.infrastructure.api.schemas.tasks import TaskResponse
from app.infrastructure.api.schemas.users import AssignedTaskPageResponse, UserResponse

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: {"model": ErrorResponse}},
)
async def get_me(
    actor_id: CurrentUserId,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> UserResponse:
    use_case = GetCurrentUser(uow)
    result = await use_case.execute(GetCurrentUserCommand(actor_id=actor_id))
    return UserResponse.model_validate(result, from_attributes=True)


@router.get(
    "/me/tasks",
    response_model=AssignedTaskPageResponse,
    responses={401: {"model": ErrorResponse}},
)
async def list_my_assigned_tasks(
    actor_id: CurrentUserId,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AssignedTaskPageResponse:
    use_case = ListMyAssignedTasks(uow)
    result = await use_case.execute(
        ListMyAssignedTasksCommand(actor_id=actor_id, limit=limit, offset=offset)
    )
    return AssignedTaskPageResponse(
        items=[
            TaskResponse.model_validate(item, from_attributes=True)
            for item in result.items
        ],
        total=result.total,
    )
