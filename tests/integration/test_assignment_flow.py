"""Integration test for the full assignment flow against a real Postgres
database (task-assignment spec, end to end): assign -> observe a recorded
notification -> reassign -> unassign -> `GET /users/me/tasks` as the
assignee.

`get_notifier` is overridden with a `RecordingNotifier` instead of the
real `BackgroundTaskNotifier` -- a test double substituted for FastAPI's
`BackgroundTasks` -- so the notification is observable synchronously
within the test instead of racing the HTTP response.
"""

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.api.dependencies import get_notifier, get_session_factory
from app.main import create_app
from tests.unit.fakes import RecordingNotifier

pytestmark = pytest.mark.integration


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()


@pytest_asyncio.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession], notifier: RecordingNotifier
) -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_notifier] = lambda: notifier
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


async def _user_id(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.get("/api/v1/users/me", headers=headers)
    user_id: str = response.json()["id"]
    return user_id


async def test_assign_reassign_unassign_and_my_assigned_tasks(
    client: AsyncClient, notifier: RecordingNotifier
) -> None:
    owner_headers = await _register_and_login(client, "owner-flow@example.com")
    old_assignee_headers = await _register_and_login(client, "old-flow@example.com")
    new_assignee_headers = await _register_and_login(client, "new-flow@example.com")
    old_assignee_id = await _user_id(client, old_assignee_headers)
    new_assignee_id = await _user_id(client, new_assignee_headers)

    list_response = await client.post(
        "/api/v1/lists", json={"name": "Groceries"}, headers=owner_headers
    )
    list_id = list_response.json()["id"]
    task_response = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "priority": "low"},
        headers=owner_headers,
    )
    task_id = task_response.json()["id"]

    assign_response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/assignee",
        json={"assignee_id": old_assignee_id},
        headers=owner_headers,
    )
    assert assign_response.status_code == 200
    assert assign_response.json()["assignee_id"] == old_assignee_id
    assert len(notifier.sent) == 1
    assert notifier.sent[0].to_email == "old-flow@example.com"

    reassign_response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/assignee",
        json={"assignee_id": new_assignee_id},
        headers=owner_headers,
    )
    assert reassign_response.status_code == 200
    assert len(notifier.sent) == 2
    assert notifier.sent[1].to_email == "new-flow@example.com"

    my_tasks_response = await client.get(
        "/api/v1/users/me/tasks", headers=new_assignee_headers
    )
    assert my_tasks_response.status_code == 200
    my_tasks_body = my_tasks_response.json()
    assert my_tasks_body["total"] == 1
    assert my_tasks_body["items"][0]["id"] == task_id

    old_assignee_tasks_response = await client.get(
        "/api/v1/users/me/tasks", headers=old_assignee_headers
    )
    assert old_assignee_tasks_response.json()["total"] == 0

    unassign_response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/assignee",
        json={"assignee_id": None},
        headers=owner_headers,
    )
    assert unassign_response.status_code == 200
    assert unassign_response.json()["assignee_id"] is None
    assert len(notifier.sent) == 2  # unassigning never notifies

    empty_my_tasks_response = await client.get(
        "/api/v1/users/me/tasks", headers=new_assignee_headers
    )
    assert empty_my_tasks_response.json()["total"] == 0
