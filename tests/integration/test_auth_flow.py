"""Integration test for the full auth flow against a real Postgres database
and the real Argon2/JWT adapters (user-auth spec, end to end): register ->
login -> refresh -> `/users/me`.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.api.dependencies import get_session_factory
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_register_login_refresh_me_end_to_end(client: AsyncClient) -> None:
    register_response = await client.post(
        "/api/v1/auth/register",
        json={"email": "flow@example.com", "password": "Passw0rd1"},
    )
    assert register_response.status_code == 201
    assert register_response.json()["email"] == "flow@example.com"

    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "flow@example.com", "password": "Passw0rd1"},
    )
    assert login_response.status_code == 200
    tokens = login_response.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    refresh_response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refresh_response.status_code == 200
    new_access_token = refresh_response.json()["access_token"]
    assert new_access_token

    me_response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {new_access_token}"},
    )
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "flow@example.com"


async def test_refresh_token_rejected_as_access_token_end_to_end(
    client: AsyncClient,
) -> None:
    await client.post(
        "/api/v1/auth/register",
        json={"email": "flow2@example.com", "password": "Passw0rd1"},
    )
    login_response = await client.post(
        "/api/v1/auth/login",
        json={"email": "flow2@example.com", "password": "Passw0rd1"},
    )
    refresh_token = login_response.json()["refresh_token"]

    response = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
