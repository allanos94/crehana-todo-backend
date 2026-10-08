"""Unit tests for the auth use cases against in-memory fakes (user-auth
spec: registration, login without account enumeration, token refresh,
authenticated identity lookup).
"""

from datetime import UTC, datetime

import pytest

from app.application.auth.dto import (
    GetCurrentUserCommand,
    LoginUserCommand,
    RefreshTokensCommand,
    RegisterUserCommand,
)
from app.application.auth.use_cases import (
    GetCurrentUser,
    LoginUser,
    RefreshTokens,
    RegisterUser,
)
from app.application.exceptions import InvalidCredentialsError
from app.domain.exceptions import (
    EmailAlreadyRegisteredError,
    PasswordPolicyError,
    UserNotFoundError,
)
from app.domain.user import User
from tests.unit.fakes import (
    FakePasswordHasher,
    FakeTokenService,
    FakeUnitOfWork,
    FixedClock,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


async def test_register_user_succeeds_and_hashes_the_password() -> None:
    uow = FakeUnitOfWork()
    use_case = RegisterUser(uow, FixedClock(_NOW), FakePasswordHasher())

    result = await use_case.execute(
        RegisterUserCommand(email="New@Example.com", password="Passw0rd1")
    )

    assert result.email == "new@example.com"
    stored = await uow.users.get_by_email("new@example.com")
    assert stored is not None
    assert stored.hashed_password == "hashed:Passw0rd1"
    assert stored.hashed_password != "Passw0rd1"


async def test_register_user_rejects_duplicate_email() -> None:
    uow = FakeUnitOfWork()
    existing = User.create(
        email="taken@example.com", hashed_password="hashed:x", now=_NOW
    )
    await uow.users.add(existing)
    use_case = RegisterUser(uow, FixedClock(_NOW), FakePasswordHasher())

    with pytest.raises(EmailAlreadyRegisteredError):
        await use_case.execute(
            RegisterUserCommand(email="TAKEN@example.com", password="Passw0rd1")
        )


async def test_register_user_rejects_weak_password() -> None:
    uow = FakeUnitOfWork()
    use_case = RegisterUser(uow, FixedClock(_NOW), FakePasswordHasher())

    with pytest.raises(PasswordPolicyError):
        await use_case.execute(
            RegisterUserCommand(email="weak@example.com", password="short1")
        )


async def test_login_user_succeeds_with_correct_password() -> None:
    uow = FakeUnitOfWork()
    hasher = FakePasswordHasher()
    hashed = await hasher.hash("Passw0rd1")
    user = User.create(email="user@example.com", hashed_password=hashed, now=_NOW)
    await uow.users.add(user)
    tokens = FakeTokenService()
    use_case = LoginUser(uow, hasher, tokens)

    pair = await use_case.execute(
        LoginUserCommand(email="user@example.com", password="Passw0rd1")
    )

    assert pair.access_token
    assert tokens.issued_for == [user.id]


async def test_login_user_rejects_wrong_password() -> None:
    uow = FakeUnitOfWork()
    hasher = FakePasswordHasher()
    hashed = await hasher.hash("Passw0rd1")
    user = User.create(email="user@example.com", hashed_password=hashed, now=_NOW)
    await uow.users.add(user)
    use_case = LoginUser(uow, hasher, FakeTokenService())

    with pytest.raises(InvalidCredentialsError) as wrong_password:
        await use_case.execute(
            LoginUserCommand(email="user@example.com", password="WrongPass1")
        )

    use_case_unknown = LoginUser(FakeUnitOfWork(), hasher, FakeTokenService())
    with pytest.raises(InvalidCredentialsError) as unknown_email:
        await use_case_unknown.execute(
            LoginUserCommand(email="ghost@example.com", password="Whatever1")
        )

    assert str(wrong_password.value) == str(unknown_email.value)


async def test_refresh_tokens_succeeds_for_an_existing_user() -> None:
    uow = FakeUnitOfWork()
    user = User.create(email="user@example.com", hashed_password="h", now=_NOW)
    await uow.users.add(user)
    tokens = FakeTokenService()
    issued = tokens.issue_pair(user.id)
    use_case = RefreshTokens(uow, tokens)

    pair = await use_case.execute(
        RefreshTokensCommand(refresh_token=issued.refresh_token)
    )

    assert pair.access_token


async def test_get_current_user_succeeds_for_an_existing_actor() -> None:
    uow = FakeUnitOfWork()
    user = User.create(email="user@example.com", hashed_password="h", now=_NOW)
    await uow.users.add(user)
    use_case = GetCurrentUser(uow)

    result = await use_case.execute(GetCurrentUserCommand(actor_id=user.id))

    assert result.email == "user@example.com"


async def test_get_current_user_raises_when_actor_no_longer_exists() -> None:
    uow = FakeUnitOfWork()
    use_case = GetCurrentUser(uow)

    with pytest.raises(UserNotFoundError):
        await use_case.execute(
            GetCurrentUserCommand(
                actor_id=User.create(
                    email="ghost@example.com", hashed_password="h", now=_NOW
                ).id
            )
        )
