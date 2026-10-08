"""The authenticated-identity endpoint (user-auth spec: `GET /users/me`)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.application.auth.dto import GetCurrentUserCommand
from app.application.auth.use_cases import GetCurrentUser
from app.application.ports import UnitOfWork
from app.infrastructure.api.dependencies import CurrentUserId, get_uow
from app.infrastructure.api.schemas.common import ErrorResponse
from app.infrastructure.api.schemas.users import UserResponse

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
