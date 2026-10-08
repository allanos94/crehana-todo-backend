"""HTTP-layer tests for the tasks API (tasks spec, full HTTP contract for
CRUD + status; filters/pagination/completion land in Phase 7, and the
assignee path lands in Phase 8), against fakes via `ASGITransport` +
`dependency_overrides` (design ADR-14).
"""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.domain.value_objects import TaskStatus
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

_NOW = datetime(2026, 1, 1, tzinfo=UTC)  # today() -> date(2026, 1, 1)


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


async def _create_list(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post(
        "/api/v1/lists", json={"name": "Groceries"}, headers=headers
    )
    list_id: str = response.json()["id"]
    return list_id


async def _create_task_api(
    client: AsyncClient,
    headers: dict[str, str],
    list_id: str,
    *,
    title: str = "Task",
    priority: str = "low",
) -> str:
    response = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": title, "priority": priority},
        headers=headers,
    )
    task_id: str = response.json()["id"]
    return task_id


async def test_create_returns_201_with_all_fields(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)

    response = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={
            "title": "Buy milk",
            "priority": "low",
            "due_date": "2026-01-01",
        },
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Buy milk"
    assert body["status"] == "pending"
    assert body["due_date"] == "2026-01-01"


async def test_create_returns_201_with_due_date_omitted(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)

    response = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "priority": "low"},
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["due_date"] is None


async def test_create_rejects_blank_title(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)

    response = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "   ", "priority": "low"},
        headers=headers,
    )

    assert response.status_code == 422


async def test_create_rejects_title_over_200_characters(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)

    response = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "x" * 201, "priority": "low"},
        headers=headers,
    )

    assert response.status_code == 422


async def test_create_rejects_description_over_2000_characters(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)

    response = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "description": "x" * 2001, "priority": "low"},
        headers=headers,
    )

    assert response.status_code == 422


async def test_create_rejects_invalid_priority(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)

    response = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "priority": "urgent"},
        headers=headers,
    )

    assert response.status_code == 422


async def test_create_in_another_users_list_returns_404(client: AsyncClient) -> None:
    owner_headers = await _auth_headers(client, email="owner@example.com")
    stranger_headers = await _auth_headers(client, email="stranger@example.com")
    list_id = await _create_list(client, owner_headers)

    response = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "priority": "low"},
        headers=stranger_headers,
    )

    assert response.status_code == 404


async def test_create_requires_authentication(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/lists/00000000-0000-0000-0000-000000000000/tasks",
        json={"title": "Buy milk", "priority": "low"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    ("due_date", "expected_status"),
    [
        ("2025-12-31", 422),  # past
        ("2026-01-01", 201),  # today
        ("2026-01-02", 201),  # future
        (None, 201),  # omitted
    ],
)
async def test_create_due_date_boundaries(
    client: AsyncClient, due_date: str | None, expected_status: int
) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    payload: dict[str, object] = {"title": "Buy milk", "priority": "low"}
    if due_date is not None:
        payload["due_date"] = due_date

    response = await client.post(
        f"/api/v1/lists/{list_id}/tasks", json=payload, headers=headers
    )

    assert response.status_code == expected_status


async def test_get_update_and_delete_task(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    created = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "priority": "low"},
        headers=headers,
    )
    task_id = created.json()["id"]

    get_response = await client.get(
        f"/api/v1/lists/{list_id}/tasks/{task_id}", headers=headers
    )
    assert get_response.status_code == 200

    patch_response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}",
        json={"title": "Updated title"},
        headers=headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["title"] == "Updated title"

    delete_response = await client.delete(
        f"/api/v1/lists/{list_id}/tasks/{task_id}", headers=headers
    )
    assert delete_response.status_code == 204


@pytest.mark.parametrize(
    ("due_date", "expected_status"),
    [
        ("2025-12-31", 422),  # past
        ("2026-01-01", 200),  # today
    ],
)
async def test_update_due_date_boundaries(
    client: AsyncClient, due_date: str, expected_status: int
) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    created = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "priority": "low"},
        headers=headers,
    )
    task_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}",
        json={"due_date": due_date},
        headers=headers,
    )

    assert response.status_code == expected_status


async def test_update_can_clear_due_date_to_null(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    created = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "priority": "low", "due_date": "2026-01-02"},
        headers=headers,
    )
    task_id = created.json()["id"]

    response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}",
        json={"due_date": None},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["due_date"] is None


async def test_non_owner_gets_404_on_every_verb(client: AsyncClient) -> None:
    owner_headers = await _auth_headers(client, email="owner@example.com")
    stranger_headers = await _auth_headers(client, email="stranger@example.com")
    list_id = await _create_list(client, owner_headers)
    created = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "priority": "low"},
        headers=owner_headers,
    )
    task_id = created.json()["id"]

    get_response = await client.get(
        f"/api/v1/lists/{list_id}/tasks/{task_id}", headers=stranger_headers
    )
    patch_response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}",
        json={"title": "Hacked"},
        headers=stranger_headers,
    )
    delete_response = await client.delete(
        f"/api/v1/lists/{list_id}/tasks/{task_id}", headers=stranger_headers
    )
    status_response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/status",
        json={"status": "in_progress"},
        headers=stranger_headers,
    )

    assert get_response.status_code == 404
    assert patch_response.status_code == 404
    assert delete_response.status_code == 404
    assert status_response.status_code == 404


async def test_unauthenticated_gets_401_on_every_verb(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    created = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "priority": "low"},
        headers=headers,
    )
    task_id = created.json()["id"]

    get_response = await client.get(f"/api/v1/lists/{list_id}/tasks/{task_id}")
    patch_response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}", json={"title": "Hacked"}
    )
    delete_response = await client.delete(f"/api/v1/lists/{list_id}/tasks/{task_id}")
    status_response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/status",
        json={"status": "in_progress"},
    )

    assert get_response.status_code == 401
    assert patch_response.status_code == 401
    assert delete_response.status_code == 401
    assert status_response.status_code == 401


@pytest.mark.parametrize(
    ("source", "destination", "expected_status"),
    [
        ("pending", "in_progress", 200),
        ("in_progress", "pending", 200),
        ("in_progress", "done", 200),
        ("done", "in_progress", 200),
        ("pending", "done", 409),
        ("done", "pending", 409),
        ("pending", "pending", 409),
    ],
)
async def test_status_transitions(
    client: AsyncClient,
    uow: FakeUnitOfWork,
    source: str,
    destination: str,
    expected_status: int,
) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    created = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "priority": "low"},
        headers=headers,
    )
    task_id = created.json()["id"]

    stored = await uow.tasks.get(UUID(task_id))
    assert stored is not None
    stored.status = TaskStatus(source)

    response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/status",
        json={"status": destination},
        headers=headers,
    )

    assert response.status_code == expected_status
    if expected_status == 409:
        assert response.json()["code"] == "invalid_status_transition"


async def test_list_tasks_completion_ignores_active_filters(
    client: AsyncClient, uow: FakeUnitOfWork
) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    task_ids = [
        await _create_task_api(client, headers, list_id, title=f"Task {i}")
        for i in range(4)
    ]
    done_task = await uow.tasks.get(UUID(task_ids[0]))
    assert done_task is not None
    done_task.status = TaskStatus.DONE

    response = await client.get(
        f"/api/v1/lists/{list_id}/tasks?status=pending", headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 3
    assert body["completion_percentage"] == 25.00


async def test_list_tasks_completion_zero_tasks(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)

    response = await client.get(f"/api/v1/lists/{list_id}/tasks", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["completion_percentage"] == 0.0


async def test_list_tasks_completion_rounds_to_two_decimals(
    client: AsyncClient, uow: FakeUnitOfWork
) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    task_ids = [
        await _create_task_api(client, headers, list_id, title=f"Task {i}")
        for i in range(3)
    ]
    done_task = await uow.tasks.get(UUID(task_ids[0]))
    assert done_task is not None
    done_task.status = TaskStatus.DONE

    response = await client.get(f"/api/v1/lists/{list_id}/tasks", headers=headers)

    assert response.status_code == 200
    assert response.json()["completion_percentage"] == 33.33


async def test_list_tasks_filters_by_status(
    client: AsyncClient, uow: FakeUnitOfWork
) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    pending_id = await _create_task_api(client, headers, list_id, title="Pending")
    done_id = await _create_task_api(client, headers, list_id, title="Done")
    done_task = await uow.tasks.get(UUID(done_id))
    assert done_task is not None
    done_task.status = TaskStatus.DONE

    response = await client.get(
        f"/api/v1/lists/{list_id}/tasks?status=done", headers=headers
    )

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [done_id]
    assert pending_id not in ids


async def test_list_tasks_filters_by_priority(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    low_id = await _create_task_api(client, headers, list_id, priority="low")
    high_id = await _create_task_api(client, headers, list_id, priority="high")

    response = await client.get(
        f"/api/v1/lists/{list_id}/tasks?priority=high", headers=headers
    )

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [high_id]
    assert low_id not in ids


async def test_list_tasks_combines_status_and_priority_filters(
    client: AsyncClient, uow: FakeUnitOfWork
) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    match_id = await _create_task_api(
        client, headers, list_id, title="Match", priority="high"
    )
    wrong_priority_id = await _create_task_api(
        client, headers, list_id, title="WrongPriority", priority="low"
    )
    wrong_status_id = await _create_task_api(
        client, headers, list_id, title="WrongStatus", priority="high"
    )
    wrong_status_task = await uow.tasks.get(UUID(wrong_status_id))
    assert wrong_status_task is not None
    wrong_status_task.status = TaskStatus.DONE

    response = await client.get(
        f"/api/v1/lists/{list_id}/tasks?status=pending&priority=high",
        headers=headers,
    )

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [match_id]
    assert wrong_priority_id not in ids
    assert wrong_status_id not in ids


async def test_list_tasks_pagination_total_reflects_filtered_count(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    for index in range(10):
        await _create_task_api(client, headers, list_id, title=f"Task {index}")

    response = await client.get(
        f"/api/v1/lists/{list_id}/tasks?limit=3&offset=3", headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 3
    assert body["total"] == 10


async def test_list_tasks_non_owner_returns_404(client: AsyncClient) -> None:
    owner_headers = await _auth_headers(client, email="owner@example.com")
    stranger_headers = await _auth_headers(client, email="stranger@example.com")
    list_id = await _create_list(client, owner_headers)

    response = await client.get(
        f"/api/v1/lists/{list_id}/tasks", headers=stranger_headers
    )

    assert response.status_code == 404


async def test_list_tasks_requires_authentication(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/lists/00000000-0000-0000-0000-000000000000/tasks"
    )

    assert response.status_code == 401


@pytest.mark.parametrize("limit", [0, 101])
async def test_list_tasks_rejects_limit_out_of_range(
    client: AsyncClient, limit: int
) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)

    response = await client.get(
        f"/api/v1/lists/{list_id}/tasks?limit={limit}", headers=headers
    )

    assert response.status_code == 422


async def test_list_tasks_rejects_negative_offset(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)

    response = await client.get(
        f"/api/v1/lists/{list_id}/tasks?offset=-1", headers=headers
    )

    assert response.status_code == 422


async def test_list_tasks_rejects_invalid_status_enum(client: AsyncClient) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)

    response = await client.get(
        f"/api/v1/lists/{list_id}/tasks?status=bogus", headers=headers
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


async def test_list_tasks_default_limit_and_offset(
    client: AsyncClient,
) -> None:
    headers = await _auth_headers(client)
    list_id = await _create_list(client, headers)
    for index in range(25):
        await _create_task_api(client, headers, list_id, title=f"Task {index}")

    response = await client.get(f"/api/v1/lists/{list_id}/tasks", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 20  # default limit
    assert body["total"] == 25
