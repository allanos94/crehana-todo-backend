"""Tests for the liveness and readiness health endpoints."""

from collections.abc import AsyncIterator

from httpx import ASGITransport, AsyncClient

from app.infrastructure.api.dependencies import get_session
from app.main import create_app


class _WorkingSession:
    """A fake `AsyncSession` whose `execute` always succeeds."""

    async def execute(self, *args: object, **kwargs: object) -> None:
        return None


class _BrokenSession:
    """A fake `AsyncSession` whose `execute` always raises, like a dead DB."""

    async def execute(self, *args: object, **kwargs: object) -> None:
        raise ConnectionRefusedError("database unreachable")


async def test_health_returns_200_ok() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_requires_no_auth() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200


async def test_readiness_ok_when_db_reachable() -> None:
    app = create_app()

    async def _fake_get_session() -> AsyncIterator[_WorkingSession]:
        yield _WorkingSession()

    app.dependency_overrides[get_session] = _fake_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readiness_fails_when_db_unreachable() -> None:
    app = create_app()

    async def _fake_get_session() -> AsyncIterator[_BrokenSession]:
        yield _BrokenSession()

    app.dependency_overrides[get_session] = _fake_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
