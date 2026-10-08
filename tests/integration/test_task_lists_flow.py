"""Integration test for the full task-lists flow against a real Postgres
database and the real JWT/Argon2 adapters (task-lists spec, end to end):
create -> duplicate 409 -> get -> patch -> delete -> subsequent get 404.
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


async def _register_and_login(client: AsyncClient, email: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "Passw0rd1"}
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Passw0rd1"}
    )
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


async def test_create_duplicate_get_patch_delete_end_to_end(
    client: AsyncClient,
) -> None:
    headers = await _register_and_login(client, "flow-lists@example.com")

    create_response = await client.post(
        "/api/v1/lists",
        json={"name": "Groceries", "description": "buy milk"},
        headers=headers,
    )
    assert create_response.status_code == 201
    list_id = create_response.json()["id"]

    duplicate_response = await client.post(
        "/api/v1/lists", json={"name": "GROCERIES"}, headers=headers
    )
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["code"] == "task_list_name_conflict"

    get_response = await client.get(f"/api/v1/lists/{list_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["name"] == "Groceries"

    patch_response = await client.patch(
        f"/api/v1/lists/{list_id}",
        json={"name": "Shopping", "description": "buy milk and eggs"},
        headers=headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["name"] == "Shopping"

    delete_response = await client.delete(f"/api/v1/lists/{list_id}", headers=headers)
    assert delete_response.status_code == 204

    final_get_response = await client.get(f"/api/v1/lists/{list_id}", headers=headers)
    assert final_get_response.status_code == 404
