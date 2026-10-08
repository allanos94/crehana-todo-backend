"""Strict CORS policy (security-hardening spec: strict CORS policy, both
scenarios).
"""

from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.infrastructure.config import get_settings
from app.main import create_app

_ALLOWED_ORIGIN = "https://app.example.com"
_DISALLOWED_ORIGIN = "https://evil.example.com"


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_allowed_origin_receives_cors_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", f'["{_ALLOWED_ORIGIN}"]')
    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"Origin": _ALLOWED_ORIGIN})

    assert response.headers.get("access-control-allow-origin") == _ALLOWED_ORIGIN


async def test_disallowed_origin_does_not_receive_permissive_cors_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", f'["{_ALLOWED_ORIGIN}"]')
    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"Origin": _DISALLOWED_ORIGIN})

    assert "access-control-allow-origin" not in response.headers
