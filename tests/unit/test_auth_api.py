"""HTTP-layer tests for the auth/users API (user-auth spec, full HTTP
contract): register, login, refresh, and `/users/me`, against fakes via
`ASGITransport` + `dependency_overrides` (design ADR-14).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.infrastructure.api.dependencies import (
    get_clock,
    get_password_hasher,
    get_token_service,
    get_uow,
)
from app.main import create_app
from tests.unit.fakes import (
    FakePasswordHasher,
    FakeTokenService,
    FakeUnitOfWork,
    FixedClock,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest_asyncio.fixture
async def client(uow: FakeUnitOfWork) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_uow] = lambda: uow
    app.dependency_overrides[get_clock] = lambda: FixedClock(_NOW)
    app.dependency_overrides[get_password_hasher] = lambda: FakePasswordHasher()
    app.dependency_overrides[get_token_service] = lambda: FakeTokenService()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def _register(client: AsyncClient, email: str = "user@example.com") -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "Passw0rd1"},
    )
    assert response.status_code == 201


async def _login(
    client: AsyncClient, email: str = "user@example.com"
) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Passw0rd1"},
    )
    assert response.status_code == 200
    return dict(response.json())


async def test_register_returns_201_and_never_echoes_the_password(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "Passw0rd1"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert "password" not in body
    assert "hashed_password" not in body


async def test_register_rejects_duplicate_email_any_case(client: AsyncClient) -> None:
    await _register(client, email="dup@example.com")

    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "DUP@example.com", "password": "Passw0rd1"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "email_already_registered"


@pytest.mark.parametrize(
    "password",
    ["short1", "a" * 129 + "1", "OnlyLetters", "12345678"],
    ids=["too_short", "too_long", "missing_digit", "missing_letter"],
)
async def test_register_rejects_password_policy_violations(
    client: AsyncClient, password: str
) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": password},
    )

    assert response.status_code == 422


async def test_login_returns_200_with_both_tokens(client: AsyncClient) -> None:
    await _register(client)

    tokens = await _login(client)

    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"


async def test_login_wrong_password_and_unknown_email_share_the_same_401(
    client: AsyncClient,
) -> None:
    await _register(client)

    wrong_password = await client.post(
        "/api/v1/auth/login",
        json={"email": "user@example.com", "password": "WrongPass1"},
    )
    unknown_email = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@example.com", "password": "Whatever1"},
    )

    assert wrong_password.status_code == 401
    assert unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


async def test_refresh_returns_200_with_a_new_access_token(client: AsyncClient) -> None:
    await _register(client)
    tokens = await _login(client)

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_refresh_rejects_an_access_token_presented_as_refresh(
    client: AsyncClient,
) -> None:
    await _register(client)
    tokens = await _login(client)

    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["access_token"]}
    )

    assert response.status_code == 401


async def test_get_me_rejects_a_refresh_token_presented_as_access(
    client: AsyncClient,
) -> None:
    await _register(client)
    tokens = await _login(client)

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )

    assert response.status_code == 401


async def test_get_me_returns_200_for_a_valid_access_token(client: AsyncClient) -> None:
    await _register(client)
    tokens = await _login(client)

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"


async def test_get_me_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["code"] == "not_authenticated"
    assert response.headers.get("www-authenticate") == "Bearer"


async def test_get_me_rejects_a_malformed_token(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
