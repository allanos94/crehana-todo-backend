"""Tests for the shared error-response schemas (design ADR-13)."""

from app.infrastructure.api.schemas.common import ErrorDetail, ErrorResponse


def test_error_response_omits_details_when_none() -> None:
    response = ErrorResponse(code="task_not_found", message="Task not found")
    assert response.model_dump(exclude_none=True) == {
        "code": "task_not_found",
        "message": "Task not found",
    }


def test_error_response_includes_details_when_present() -> None:
    detail = ErrorDetail(field="body.name", message="too long", type="string_too_long")
    response = ErrorResponse(
        code="validation_error", message="Request validation failed", details=[detail]
    )
    dumped = response.model_dump()
    assert dumped["details"] == [
        {"field": "body.name", "message": "too long", "type": "string_too_long"}
    ]
