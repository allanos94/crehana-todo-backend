"""HTTP-layer tests for the task-lists API (task-lists spec, full HTTP
contract): create, retrieve, list, update, delete, against fakes via
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


async def _auth_headers(
    client: AsyncClient, email: str = "owner@example.com"
) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "Passw0rd1"}
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Passw0rd1"}
    )
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


async def test_create_returns_201(client: AsyncClient) -> None:
    headers = await _auth_headers(client)

    response = await client.post(
        "/api/v1/lists",
        json={"name": "Groceries", "description": "buy milk"},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Groceries"
    assert body["description"] == "buy milk"


async def test_create_rejects_blank_name(client: AsyncClient) -> None:
    headers = await _auth_headers(client)

    response = await client.post("/api/v1/lists", json={"name": "   "}, headers=headers)

    assert response.status_code == 422


async def test_create_rejects_name_over_120_characters(client: AsyncClient) -> None:
    headers = await _auth_headers(client)

    response = await client.post(
        "/api/v1/lists", json={"name": "x" * 121}, headers=headers
    )

    assert response.status_code == 422


async def test_create_rejects_description_over_2000_characters(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)

    response = await client.post(
        "/api/v1/lists",
        json={"name": "Groceries", "description": "x" * 2001},
        headers=headers,
    )

    assert response.status_code == 422


async def test_create_requires_authentication(client: AsyncClient) -> None:
    response = await client.post("/api/v1/lists", json={"name": "Groceries"})

    assert response.status_code == 401


async def test_create_rejects_duplicate_name_any_case(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    await client.post("/api/v1/lists", json={"name": "Groceries"}, headers=headers)

    response = await client.post(
        "/api/v1/lists", json={"name": "GROCERIES"}, headers=headers
    )

    assert response.status_code == 409
    assert response.json()["code"] == "task_list_name_conflict"


async def test_get_nonexistent_list_returns_404(client: AsyncClient) -> None:
    headers = await _auth_headers(client)

    response = await client.get(
        "/api/v1/lists/00000000-0000-0000-0000-000000000000", headers=headers
    )

    assert response.status_code == 404


async def test_non_owner_cannot_get_patch_or_delete_another_users_list(
    client: AsyncClient,
) -> None:
    owner_headers = await _auth_headers(client, email="owner@example.com")
    stranger_headers = await _auth_headers(client, email="stranger@example.com")
    created = await client.post(
        "/api/v1/lists", json={"name": "Groceries"}, headers=owner_headers
    )
    list_id = created.json()["id"]

    get_response = await client.get(
        f"/api/v1/lists/{list_id}", headers=stranger_headers
    )
    patch_response = await client.patch(
        f"/api/v1/lists/{list_id}", json={"name": "Hacked"}, headers=stranger_headers
    )
    delete_response = await client.delete(
        f"/api/v1/lists/{list_id}", headers=stranger_headers
    )

    assert get_response.status_code == 404
    assert patch_response.status_code == 404
    assert delete_response.status_code == 404


async def test_update_succeeds_for_the_owner(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    created = await client.post(
        "/api/v1/lists", json={"name": "Groceries"}, headers=headers
    )
    list_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/lists/{list_id}",
        json={"name": "Work", "description": "new description"},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Work"
    assert body["description"] == "new description"


async def test_delete_succeeds_then_subsequent_get_returns_404(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    created = await client.post(
        "/api/v1/lists", json={"name": "Groceries"}, headers=headers
    )
    list_id = created.json()["id"]

    delete_response = await client.delete(f"/api/v1/lists/{list_id}", headers=headers)
    get_response = await client.get(f"/api/v1/lists/{list_id}", headers=headers)

    assert delete_response.status_code == 204
    assert get_response.status_code == 404


async def test_list_returns_only_the_callers_lists(client: AsyncClient) -> None:
    owner_headers = await _auth_headers(client, email="owner@example.com")
    other_headers = await _auth_headers(client, email="other@example.com")
    await client.post("/api/v1/lists", json={"name": "Work"}, headers=owner_headers)
    await client.post(
        "/api/v1/lists", json={"name": "Other owner's list"}, headers=other_headers
    )

    response = await client.get("/api/v1/lists", headers=owner_headers)

    assert response.status_code == 200
    names = [item["name"] for item in response.json()]
    assert names == ["Work"]
