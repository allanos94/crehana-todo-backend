"""Rate limiting on authentication endpoints (security-hardening spec: rate
limiting, both scenarios). The dedicated test here is the only place that
enables rate limiting with a deliberately low limit; every other suite runs
with it disabled (default) so pre-existing tests never bleed into this one.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.infrastructure.api.dependencies import get_clock, get_uow
from app.infrastructure.config import get_settings
from app.infrastructure.security.rate_limit import limiter
from app.main import create_app
from tests.unit.fakes import FakeUnitOfWork, FixedClock

_NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _reset_limiter(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("AUTH_RATE_LIMIT", "3/minute")
    get_settings.cache_clear()
    monkeypatch.setattr(limiter, "enabled", True)
    limiter.reset()
    yield
    limiter.reset()
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    app.dependency_overrides[get_uow] = lambda: FakeUnitOfWork()
    app.dependency_overrides[get_clock] = lambda: FixedClock(_NOW)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


async def test_requests_within_the_limit_succeed(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Passw0rd1"},
    )

    assert response.status_code == 401


async def test_requests_exceeding_the_limit_are_throttled(
    client: AsyncClient,
) -> None:
    for _ in range(3):
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "Passw0rd1"},
        )
        assert response.status_code == 401

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "Passw0rd1"},
    )

    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "rate_limited"
