"""Security response headers (security-hardening spec: security response
headers, both the plain-HTTP and simulated-HTTPS scenarios).
"""

from httpx import ASGITransport, AsyncClient

from app.main import create_app


async def test_security_headers_present_on_plain_http_response() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "strict-transport-security" not in response.headers


async def test_hsts_header_present_when_request_is_https() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="https://test") as client:
        response = await client.get("/health")

    assert response.headers["strict-transport-security"].startswith("max-age=")


async def test_hsts_header_present_behind_trusted_forwarded_proto() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health", headers={"X-Forwarded-Proto": "https"})

    assert response.headers["strict-transport-security"].startswith("max-age=")
