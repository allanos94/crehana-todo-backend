"""Auth endpoints (user-auth spec): register, login, refresh."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.application.auth.dto import (
    LoginUserCommand,
    RefreshTokensCommand,
    RegisterUserCommand,
)
from app.application.auth.use_cases import LoginUser, RefreshTokens, RegisterUser
from app.application.ports import Clock, PasswordHasher, TokenService, UnitOfWork
from app.infrastructure.api.dependencies import (
    get_clock,
    get_password_hasher,
    get_token_service,
    get_uow,
)
from app.infrastructure.api.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPairResponse,
)
from app.infrastructure.api.schemas.common import ErrorResponse
from app.infrastructure.api.schemas.users import UserResponse
from app.infrastructure.security.rate_limit import auth_rate_limit, limiter

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
@limiter.limit(auth_rate_limit)
async def register(
    request: Request,
    payload: RegisterRequest,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    clock: Annotated[Clock, Depends(get_clock)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
) -> UserResponse:
    use_case = RegisterUser(uow, clock, hasher)
    result = await use_case.execute(
        RegisterUserCommand(email=payload.email, password=payload.password)
    )
    return UserResponse.model_validate(result, from_attributes=True)


@router.post(
    "/login",
    response_model=TokenPairResponse,
    responses={401: {"model": ErrorResponse}},
)
@limiter.limit(auth_rate_limit)
async def login(
    request: Request,
    payload: LoginRequest,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    hasher: Annotated[PasswordHasher, Depends(get_password_hasher)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> TokenPairResponse:
    use_case = LoginUser(uow, hasher, tokens)
    pair = await use_case.execute(
        LoginUserCommand(email=payload.email, password=payload.password)
    )
    return TokenPairResponse.model_validate(pair, from_attributes=True)


@router.post(
    "/refresh",
    response_model=TokenPairResponse,
    responses={401: {"model": ErrorResponse}},
)
@limiter.limit(auth_rate_limit)
async def refresh(
    request: Request,
    payload: RefreshRequest,
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> TokenPairResponse:
    use_case = RefreshTokens(uow, tokens)
    pair = await use_case.execute(
        RefreshTokensCommand(refresh_token=payload.refresh_token)
    )
    return TokenPairResponse.model_validate(pair, from_attributes=True)
