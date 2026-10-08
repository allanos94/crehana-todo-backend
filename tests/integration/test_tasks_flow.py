"""Integration test for the full tasks flow against a real Postgres
database and the real JWT/Argon2 adapters (tasks spec, end to end): create
list -> create task -> update -> status transitions including a rejected
409 -> delete -> subsequent get 404.
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


async def test_create_update_status_transitions_and_delete_end_to_end(
    client: AsyncClient,
) -> None:
    headers = await _register_and_login(client, "flow-tasks@example.com")
    list_response = await client.post(
        "/api/v1/lists", json={"name": "Groceries"}, headers=headers
    )
    list_id = list_response.json()["id"]

    create_response = await client.post(
        f"/api/v1/lists/{list_id}/tasks",
        json={"title": "Buy milk", "priority": "low"},
        headers=headers,
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]
    assert create_response.json()["status"] == "pending"

    update_response = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}",
        json={"title": "Buy oat milk", "priority": "high"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Buy oat milk"
    assert update_response.json()["priority"] == "high"

    to_in_progress = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/status",
        json={"status": "in_progress"},
        headers=headers,
    )
    assert to_in_progress.status_code == 200
    assert to_in_progress.json()["status"] == "in_progress"

    rejected_same_status = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/status",
        json={"status": "in_progress"},
        headers=headers,
    )
    assert rejected_same_status.status_code == 409
    assert rejected_same_status.json()["code"] == "invalid_status_transition"

    to_done = await client.patch(
        f"/api/v1/lists/{list_id}/tasks/{task_id}/status",
        json={"status": "done"},
        headers=headers,
    )
    assert to_done.status_code == 200
    assert to_done.json()["status"] == "done"

    delete_response = await client.delete(
        f"/api/v1/lists/{list_id}/tasks/{task_id}", headers=headers
    )
    assert delete_response.status_code == 204

    final_get_response = await client.get(
        f"/api/v1/lists/{list_id}/tasks/{task_id}", headers=headers
    )
    assert final_get_response.status_code == 404


async def test_filtered_listing_and_completion(client: AsyncClient) -> None:
    """Real-DB end to end (tasks spec: filtered/paginated listing with
    completion; design ADR-10): 10 tasks with mixed statuses/priorities,
    then assertions over pagination and the list-wide completion
    percentage, which must ignore the active filter."""
    headers = await _register_and_login(client, "flow-filters@example.com")
    list_response = await client.post(
        "/api/v1/lists", json={"name": "Groceries"}, headers=headers
    )
    list_id = list_response.json()["id"]

    task_ids: list[str] = []
    for index in range(10):
        priority = "high" if index % 2 == 0 else "low"
        created = await client.post(
            f"/api/v1/lists/{list_id}/tasks",
            json={"title": f"Task {index}", "priority": priority},
            headers=headers,
        )
        task_ids.append(created.json()["id"])

    # Move 3 tasks to done through the valid transition sequence
    # (pending -> in_progress -> done) so completion reflects 3/10 tasks.
    for task_id in task_ids[:3]:
        await client.patch(
            f"/api/v1/lists/{list_id}/tasks/{task_id}/status",
            json={"status": "in_progress"},
            headers=headers,
        )
        await client.patch(
            f"/api/v1/lists/{list_id}/tasks/{task_id}/status",
            json={"status": "done"},
            headers=headers,
        )

    filtered_response = await client.get(
        f"/api/v1/lists/{list_id}/tasks?status=pending", headers=headers
    )
    assert filtered_response.status_code == 200
    filtered_body = filtered_response.json()
    assert filtered_body["total"] == 7
    assert len(filtered_body["items"]) == 7
    assert filtered_body["completion_percentage"] == 30.00

    priority_response = await client.get(
        f"/api/v1/lists/{list_id}/tasks?priority=high", headers=headers
    )
    assert priority_response.status_code == 200
    assert priority_response.json()["total"] == 5

    page_response = await client.get(
        f"/api/v1/lists/{list_id}/tasks?limit=4&offset=8", headers=headers
    )
    assert page_response.status_code == 200
    page_body = page_response.json()
    assert len(page_body["items"]) == 2  # only 2 remain after offset 8
    assert page_body["total"] == 10
    assert page_body["completion_percentage"] == 30.00
