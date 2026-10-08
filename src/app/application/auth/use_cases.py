"""Auth use cases (user-auth spec): registration, login without account
enumeration, token refresh, and authenticated identity lookup.
"""

from app.application.auth.dto import (
    CurrentUserResult,
    GetCurrentUserCommand,
    LoginUserCommand,
    RefreshTokensCommand,
    RegisterUserCommand,
    RegisterUserResult,
)
from app.application.exceptions import InvalidCredentialsError
from app.application.ports import (
    Clock,
    PasswordHasher,
    TokenPair,
    TokenService,
    TokenType,
    UnitOfWork,
)
from app.domain.exceptions import EmailAlreadyRegisteredError, UserNotFoundError
from app.domain.user import User
from app.domain.value_objects import validate_password_policy


def _normalize_email(email: str) -> str:
    return email.strip().lower()


class RegisterUser:
    """Create a new `User` with a hashed password (user-auth spec:
    registration, password policy, duplicate-email rejection)."""

    def __init__(self, uow: UnitOfWork, clock: Clock, hasher: PasswordHasher) -> None:
        self._uow = uow
        self._clock = clock
        self._hasher = hasher

    async def execute(self, command: RegisterUserCommand) -> RegisterUserResult:
        validate_password_policy(command.password)
        email = _normalize_email(command.email)
        hashed = await self._hasher.hash(command.password)
        async with self._uow:
            existing = await self._uow.users.get_by_email(email)
            if existing is not None:
                raise EmailAlreadyRegisteredError()
            user = User.create(
                email=email, hashed_password=hashed, now=self._clock.now()
            )
            await self._uow.users.add(user)
            await self._uow.commit()
        return RegisterUserResult(
            id=user.id, email=user.email, created_at=user.created_at
        )


class LoginUser:
    """Authenticate by email/password without revealing account existence
    on failure (user-auth spec: identical error for wrong password and
    unknown email, timing-equalized via the hasher's dummy hash)."""

    def __init__(
        self, uow: UnitOfWork, hasher: PasswordHasher, tokens: TokenService
    ) -> None:
        self._uow = uow
        self._hasher = hasher
        self._tokens = tokens

    async def execute(self, command: LoginUserCommand) -> TokenPair:
        email = _normalize_email(command.email)
        async with self._uow:
            user = await self._uow.users.get_by_email(email)
        hashed = user.hashed_password if user is not None else self._hasher.dummy_hash
        password_ok = await self._hasher.verify(command.password, hashed)
        if user is None or not password_ok:
            raise InvalidCredentialsError()
        return self._tokens.issue_pair(user.id)


class RefreshTokens:
    """Issue a fresh token pair from a valid, unexpired refresh token
    (user-auth spec: token refresh; the user must still exist)."""

    def __init__(self, uow: UnitOfWork, tokens: TokenService) -> None:
        self._uow = uow
        self._tokens = tokens

    async def execute(self, command: RefreshTokensCommand) -> TokenPair:
        user_id = self._tokens.decode(command.refresh_token, TokenType.REFRESH)
        async with self._uow:
            user = await self._uow.users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        return self._tokens.issue_pair(user.id)


class GetCurrentUser:
    """Look up the authenticated actor's own identity (user-auth spec:
    authenticated identity lookup)."""

    def __init__(self, uow: UnitOfWork) -> None:
        self._uow = uow

    async def execute(self, command: GetCurrentUserCommand) -> CurrentUserResult:
        async with self._uow:
            user = await self._uow.users.get_by_id(command.actor_id)
        if user is None:
            raise UserNotFoundError()
        return CurrentUserResult(
            id=user.id, email=user.email, created_at=user.created_at
        )
