"""HTTP-layer tests for the error contract (api-error-contract spec).

A minimal throwaway app, with one route per domain exception category plus
one route raising an unhandled `Exception`, exercises
`register_exception_handlers` end to end over ASGI.
"""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.domain.exceptions import (
    DueDateInPastError,
    EmailAlreadyRegisteredError,
    UserNotFoundError,
)
from app.infrastructure.api.errors import register_exception_handlers


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-found")
    async def _not_found() -> None:
        raise UserNotFoundError()

    @app.get("/conflict")
    async def _conflict() -> None:
        raise EmailAlreadyRegisteredError()

    @app.get("/unprocessable")
    async def _unprocessable() -> None:
        raise DueDateInPastError()

    @app.post("/validate-me")
    async def _validate_me(name: str) -> dict[str, str]:
        return {"name": name}

    @app.get("/boom")
    async def _boom() -> None:
        raise RuntimeError("something broke internally, with a secret path /etc/passwd")

    return app


async def test_not_found_error_follows_the_contract() -> None:
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/not-found")

    assert response.status_code == 404
    body = response.json()
    assert set(body.keys()) == {"code", "message"}
    assert body["code"] == "user_not_found"


async def test_conflict_error_follows_the_contract() -> None:
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/conflict")

    assert response.status_code == 409
    assert response.json()["code"] == "email_already_registered"


async def test_business_rule_violation_follows_the_contract() -> None:
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/unprocessable")

    assert response.status_code == 422
    assert response.json()["code"] == "due_date_in_past"


async def test_request_validation_error_follows_the_contract_with_details() -> None:
    app = _build_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/validate-me", json={})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert "details" in body
    assert isinstance(body["details"], list)
    assert body["details"]


async def test_unhandled_exception_does_not_leak_internals() -> None:
    app = _build_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert set(body.keys()) == {"code", "message"}
    assert body["code"] == "internal_error"
    assert "secret" not in body["message"]
    assert "/etc/passwd" not in body["message"]
    assert "RuntimeError" not in body["message"]
