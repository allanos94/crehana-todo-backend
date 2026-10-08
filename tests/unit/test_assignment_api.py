"""HTTP-layer tests for the assignment API (task-assignment spec): owner
assigns/unassigns/reassigns, `GET /users/me/tasks`, and the full
non-owner-assignee matrix (an assignee may change status but nothing
else; a stranger gets 404 everywhere), against fakes via `ASGITransport` +
`dependency_overrides` (design ADR-14).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.infrastructure.api.dependencies import (
    get_clock,
    get_notifier,
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
    RecordingNotifier,
)

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def uow() -> FakeUnitOfWork:
    return FakeUnitOfWork()


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest_asyncio.fixture
async def client(
    uow: FakeUnitOfWork, notifier: RecordingNotifier
) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_uow] = lambda: uow
    app.dependency_overrides[get_clock] = lambda: FixedClock(_NOW)
    app.dependency_overrides[get_password_hasher] = lambda: FakePasswordHasher()
    app.dependency_overrides[get_token_service] = lambda: FakeTokenService()
    app.dependency_overrides[get_notifier] = lambda: notifier
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def _auth_headers(client: AsyncClient, email: str) -> dict[str, str]:
    await client.post(
        "/api/v1/auth/register", json={"email": email, "password": "Passw0rd1"}
    )
    response = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "Passw0rd1"}
    )
    access_token = response.json()["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


async def _create_list(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/lists", json={"name": "Groceries"}, headers=headers
    )
    list_id: str = response.json()["id"]
    return list_id


async def _create_task(
    client: AsyncClient, headers: dict[str, str], list_id: str
) -> str:
    response = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "priority": "low"},
        headers=headers,
    )
    task_id: str = response.json()["id"]
    return task_id


async def test_owner_assigns_task_returns_200(
    client: AsyncClient, notifier: RecordingNotifier
) -> None:
    owner_headers = await _auth_headers(client, "owner@example.com")
    await _auth_headers(client, "assignee@example.com")
    list_id = await _create_list(client, owner_headers)
    task_id = await _create_task(client, owner_headers, list_id)
    assignee_me = await client.get(
        "/api/v1/users/me", headers=await _auth_headers(client, "assignee@example.com")
    )
    assignee_id = assignee_me.json()["id"]

    response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/assignee",
        json={"assignee_id": assignee_id},
        headers=owner_headers,
    )

    assert response.status_code == 200
    assert response.json()["assignee_id"] == assignee_id
    assert len(notifier.sent) == 1


async def test_assign_to_unknown_user_returns_422(client: AsyncClient) -> None:
    owner_headers = await _auth_headers(client, "owner@example.com")
    list_id = await _create_list(client, owner_headers)
    task_id = await _create_task(client, owner_headers, list_id)

    response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/assignee",
        json={"assignee_id": "00000000-0000-0000-0000-000000000000"},
        headers=owner_headers,
    )

    assert response.status_code == 422
    assert response.json()["code"] == "assignee_not_found"


async def test_non_owner_cannot_assign_returns_404(client: AsyncClient) -> None:
    owner_headers = await _auth_headers(client, "owner@example.com")
    stranger_headers = await _auth_headers(client, "stranger@example.com")
    list_id = await _create_list(client, owner_headers)
    task_id = await _create_task(client, owner_headers, list_id)

    response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/assignee",
        json={"assignee_id": None},
        headers=stranger_headers,
    )

    assert response.status_code == 404


async def test_assign_requires_authentication(client: AsyncClient) -> None:
    owner_headers = await _auth_headers(client, "owner@example.com")
    list_id = await _create_list(client, owner_headers)
    task_id = await _create_task(client, owner_headers, list_id)

    response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/assignee",
        json={"assignee_id": None},
    )

    assert response.status_code == 401


async def test_get_my_assigned_tasks_scoped_to_caller(client: AsyncClient) -> None:
    owner_headers = await _auth_headers(client, "owner@example.com")
    assignee_headers = await _auth_headers(client, "assignee@example.com")
    assignee_id = (
        await client.get("/api/v1/users/me", headers=assignee_headers)
    ).json()["id"]
    list_id = await _create_list(client, owner_headers)
    assigned_task_id = await _create_task(client, owner_headers, list_id)
    await _create_task(client, owner_headers, list_id)  # not assigned to anyone
    await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{assigned_task_id}/assignee",
        json={"assignee_id": assignee_id},
        headers=owner_headers,
    )

    response = await client.get("/api/v1/users/me/tasks", headers=assignee_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == assigned_task_id
    assert body["items"][0]["list_id"] == list_id


async def test_get_my_assigned_tasks_empty_for_a_user_with_none(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client, "lonely@example.com")

    response = await client.get("/api/v1/users/me/tasks", headers=headers)

    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


async def test_get_my_assigned_tasks_requires_authentication(
    client: AsyncClient,
) -> None:
    response = await client.get("/api/v1/users/me/tasks")

    assert response.status_code == 401


async def test_assignee_can_change_status_of_their_assigned_task(
    client: AsyncClient,
) -> None:
    owner_headers = await _auth_headers(client, "owner@example.com")
    assignee_headers = await _auth_headers(client, "assignee@example.com")
    assignee_id = (
        await client.get("/api/v1/users/me", headers=assignee_headers)
    ).json()["id"]
    list_id = await _create_list(client, owner_headers)
    task_id = await _create_task(client, owner_headers, list_id)
    await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/assignee",
        json={"assignee_id": assignee_id},
        headers=owner_headers,
    )

    response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/status",
        json={"status": "in_progress"},
        headers=assignee_headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


@pytest.mark.parametrize(
    ("method", "path_suffix", "json_body"),
    [
        ("PATCH", "", {"title": "Hijacked"}),
        ("DELETE", "", None),
        ("PATCH", "/assignee", {"assignee_id": None}),
    ],
)
async def test_assignee_cannot_edit_delete_or_reassign(
    client: AsyncClient,
    method: str,
    path_suffix: str,
    json_body: dict[str, object] | None,
) -> None:
    owner_headers = await _auth_headers(client, "owner@example.com")
    assignee_headers = await _auth_headers(client, "assignee@example.com")
    assignee_id = (
        await client.get("/api/v1/users/me", headers=assignee_headers)
    ).json()["id"]
    list_id = await _create_list(client, owner_headers)
    task_id = await _create_task(client, owner_headers, list_id)
    await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/assignee",
        json={"assignee_id": assignee_id},
        headers=owner_headers,
    )

    response = await client.request(
        method,
        f"/api/v1/lists/{list_id}/tasks/{task_id}{path_suffix}",
        json=json_body,
        headers=assignee_headers,
    )

    assert response.status_code == 404


async def test_assignee_cannot_see_the_rest_of_the_owners_list(
    client: AsyncClient,
) -> None:
    owner_headers = await _auth_headers(client, "owner@example.com")
    assignee_headers = await _auth_headers(client, "assignee@example.com")
    assignee_id = (
        await client.get("/api/v1/users/me", headers=assignee_headers)
    ).json()["id"]
    list_id = await _create_list(client, owner_headers)
    task_id = await _create_task(client, owner_headers, list_id)
    await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/assignee",
        json={"assignee_id": assignee_id},
        headers=owner_headers,
    )

    get_list_response = await client.get(
        f"/api/v1/lists/{list_id}", headers=assignee_headers
    )
    list_tasks_response = await client.get(
        f"/api/v1/lists/{list_id}/tasks", headers=assignee_headers
    )

    assert get_list_response.status_code == 404
    assert list_tasks_response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path_suffix", "json_body"),
    [
        ("GET", "", None),
        ("PATCH", "", {"title": "Hijacked"}),
        ("DELETE", "", None),
        ("PATCH", "/status", {"status": "in_progress"}),
        ("PATCH", "/assignee", {"assignee_id": None}),
    ],
)
async def test_stranger_gets_404_everywhere(
    client: AsyncClient,
    method: str,
    path_suffix: str,
    json_body: dict[str, object] | None,
) -> None:
    owner_headers = await _auth_headers(client, "owner@example.com")
    stranger_headers = await _auth_headers(client, "stranger@example.com")
    list_id = await _create_list(client, owner_headers)
    task_id = await _create_task(client, owner_headers, list_id)

    response = await client.request(
        method,
        f"/api/v1/lists/{list_id}/tasks/{task_id}{path_suffix}",
        json=json_body,
        headers=stranger_headers,
    )

    assert response.status_code == 404

    list_response = await client.get(
        f"/api/v1/lists/{list_id}", headers=stranger_headers
    )
    list_tasks_response = await client.get(
        f"/api/v1/lists/{list_id}/tasks", headers=stranger_headers
    )
    assert list_response.status_code == 404
    assert list_tasks_response.status_code == 404
